"""Read this CUDA process's WDDM budget on its matching DXGI adapter.

No CUDA context is created. Construct only inside an already initialized CUDA
worker. Local/non-local segment usage is driver accounting, not proof of PCIe
traffic, paging, or CUDA tensor residency. No reservations or settings are changed.
"""
import ctypes as c
import os
import ntpath
import uuid


class Guid(c.Structure):
    _fields_ = [('data1', c.c_uint32), ('data2', c.c_uint16), ('data3', c.c_uint16), ('data4', c.c_ubyte * 8)]

    @classmethod
    def parse(cls, value):
        return cls.from_buffer_copy(uuid.UUID(value).bytes_le)


class Luid(c.Structure):
    _fields_ = [('low', c.c_uint32), ('high', c.c_int32)]


class MemoryInfo(c.Structure):
    _fields_ = [(name, c.c_uint64) for name in ('budget', 'usage', 'available_reservation', 'reservation')]


def method(pointer, slot, result, *arguments):
    table = c.cast(pointer, c.POINTER(c.POINTER(c.c_void_p))).contents
    return c.WINFUNCTYPE(result, c.c_void_p, *arguments)(table[slot])


def check(code, operation):
    if code:
        raise OSError('%s returned 0x%08x' % (operation, code & 0xffffffff))


class AdapterMemory:
    def __init__(self):
        if os.name != 'nt':
            raise OSError('WDDM memory accounting requires Windows')
        self.adapter = c.c_void_p()
        system = ntpath.join(os.environ.get('SystemRoot', r'C:\Windows'), 'System32')
        self.cuda, self.dxgi = c.WinDLL(ntpath.join(system, 'nvcuda.dll')), c.WinDLL(ntpath.join(system, 'dxgi.dll'))
        self.cuda.cuCtxGetDevice.argtypes = [c.POINTER(c.c_int)]
        self.cuda.cuCtxGetDevice.restype = c.c_int
        self.cuda.cuDeviceGetLuid.argtypes = [c.c_void_p, c.POINTER(c.c_uint32), c.c_int]
        self.cuda.cuDeviceGetLuid.restype = c.c_int
        device, luid, mask = c.c_int(), Luid(), c.c_uint32()
        check(self.cuda.cuCtxGetDevice(c.byref(device)), 'cuCtxGetDevice')
        check(self.cuda.cuDeviceGetLuid(c.byref(luid), c.byref(mask), device), 'cuDeviceGetLuid')
        if not mask.value or mask.value & (mask.value - 1):
            raise OSError('CUDA did not identify one WDDM adapter node')
        self.node = mask.value.bit_length() - 1
        self.identity = dict(cuda_device=device.value, node=self.node,
                             adapter_luid='%08x:%08x' % (luid.high & 0xffffffff, luid.low))
        factory = c.c_void_p()
        factory_iid = Guid.parse('1bc6ea02-ef36-464f-bf0c-21ca39e5168a')
        adapter_iid = Guid.parse('645967a4-1392-4310-a798-8053ce3e93fd')
        self.dxgi.CreateDXGIFactory1.argtypes = [c.POINTER(Guid), c.POINTER(c.c_void_p)]
        self.dxgi.CreateDXGIFactory1.restype = c.c_int32
        check(self.dxgi.CreateDXGIFactory1(c.byref(factory_iid), c.byref(factory)), 'CreateDXGIFactory1')
        try:
            # Slots and ABI follow the Windows SDK IDXGIFactory4/IDXGIAdapter3.
            enum = method(factory, 26, c.c_int32, Luid, c.POINTER(Guid), c.POINTER(c.c_void_p))
            check(enum(factory, luid, c.byref(adapter_iid), c.byref(self.adapter)), 'EnumAdapterByLuid')
        except BaseException:
            self.close()
            raise
        finally:
            if factory:
                method(factory, 2, c.c_uint32)(factory)
        if not self.adapter:
            raise OSError('DXGI returned no matching adapter')

    def sample(self):
        if not self.adapter:
            raise OSError('DXGI adapter is closed')
        query = method(self.adapter, 14, c.c_int32, c.c_uint32, c.c_int32, c.POINTER(MemoryInfo))
        result = {}
        for group, name in ((0, 'local'), (1, 'nonlocal')):
            value = MemoryInfo()
            check(query(self.adapter, self.node, group, c.byref(value)), 'QueryVideoMemoryInfo/' + name)
            result[name] = dict(budget_bytes=value.budget, usage_bytes=value.usage)
        return result

    def close(self):
        if self.adapter:
            pointer, self.adapter = self.adapter, c.c_void_p()
            method(pointer, 2, c.c_uint32)(pointer)
