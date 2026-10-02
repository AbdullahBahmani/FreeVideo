"""PyInstaller entry point; model modules stay out of the GUI executable."""
from freevideo_engine.modern_launcher import main

if __name__ == '__main__':
    main()
