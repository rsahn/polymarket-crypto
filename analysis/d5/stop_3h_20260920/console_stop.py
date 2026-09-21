"""Send one console Ctrl+C only after validating every attached process ID."""
import ctypes,os,time

def interrupt_console(target_pid, allowed_pids, send=False):
    k=ctypes.WinDLL('kernel32',use_last_error=True)
    k.FreeConsole()
    if not k.AttachConsole(target_pid):raise OSError(ctypes.get_last_error(),'AttachConsole failed')
    try:
        # Do not interrupt this controller. Installed only on its attached console.
        if not k.SetConsoleCtrlHandler(None,True):raise OSError('Cannot protect controller')
        a=(ctypes.c_ulong*64)();n=k.GetConsoleProcessList(a,64)
        if n>64:raise RuntimeError('Unexpected console size')
        actual=set(a[:n]);expected=set(allowed_pids)|{os.getpid()}
        if target_pid not in actual or not actual<=expected:
            raise RuntimeError(f'Console scope mismatch {actual} expected {expected}')
        if send:
            if not k.GenerateConsoleCtrlEvent(0,0):raise OSError(ctypes.get_last_error(),'Ctrl+C failed')
            time.sleep(.3)
        return sorted(actual)
    finally:
        k.FreeConsole()
        k.SetConsoleCtrlHandler(None,False)
