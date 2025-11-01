import subprocess
import time

def run_script(script_name):
    process = subprocess.Popen(['python', script_name])
    return process

def main():
    capture_image_process = None
    start_backend_process = None

    try:
        print("Starting capture_images.py (Camera)...")
        capture_image_process = run_script('capture_images.py')
        
        print("Starting app.py (Backend)...")
        start_backend_process = run_script('app.py')

        print("--- SYSTEM RUNNING ---")
        print("Press Ctrl+C to terminate both services.")
        
        while True:
            if capture_image_process.poll() is not None:
                raise Exception("Camera process terminated unexpectedly!")
            if start_backend_process.poll() is not None:
                raise Exception("Backend process terminated unexpectedly!")
            
            time.sleep(1)

    except KeyboardInterrupt:
        print('\n[INFO] Termination requested (Ctrl+C).')
    
    except Exception as e:
        print(f"\n[ERROR] {e}")

    finally:
        print('\n[INFO] Terminating child processes...')
        
        if capture_image_process and capture_image_process.poll() is None:
            capture_image_process.terminate()
            print('   - capture_images.py stopped.')
            
        if start_backend_process and start_backend_process.poll() is None:
            start_backend_process.terminate()
            print('   - app.py stopped.')
            
        print('[INFO] All services shut down.')

if __name__ == '__main__':
    main()