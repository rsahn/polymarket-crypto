"""Windows CurrentUser DPAPI and owner-only DACL; no credentials on command lines."""
import ctypes
from ctypes import wintypes as w
import os
from pathlib import Path


class Blob(ctypes.Structure):
    _fields_ = [('size', w.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]


class SecurityAttributes(ctypes.Structure):
    _fields_ = [('length', w.DWORD), ('descriptor', ctypes.c_void_p), ('inherit', w.BOOL)]


class WindowsProtection:
    def __init__(self):
        if os.name != 'nt':
            raise ValueError('WINDOWS_REQUIRED')
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.advapi = ctypes.WinDLL('advapi32', use_last_error=True)
        self.crypt = ctypes.WinDLL('crypt32', use_last_error=True)
        self.kernel.LocalFree.argtypes = [ctypes.c_void_p]
        self.kernel.LocalFree.restype = ctypes.c_void_p
        self.kernel.GetCurrentProcess.restype = w.HANDLE
        self.kernel.CloseHandle.argtypes = [w.HANDLE]
        self.advapi.OpenProcessToken.argtypes = [w.HANDLE,w.DWORD,ctypes.POINTER(w.HANDLE)]
        self.advapi.GetTokenInformation.argtypes = [w.HANDLE,ctypes.c_int,ctypes.c_void_p,w.DWORD,ctypes.POINTER(w.DWORD)]
        self.advapi.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p,ctypes.POINTER(ctypes.c_void_p)]
        self.advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [w.LPCWSTR,w.DWORD,ctypes.POINTER(ctypes.c_void_p),ctypes.POINTER(w.DWORD)]
        self.kernel.CreateDirectoryW.argtypes = [w.LPCWSTR,ctypes.POINTER(SecurityAttributes)]
        self.kernel.MoveFileExW.argtypes = [w.LPCWSTR,w.LPCWSTR,w.DWORD]
        self.crypt.CryptProtectData.argtypes = [ctypes.POINTER(Blob),w.LPCWSTR,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,w.DWORD,ctypes.POINTER(Blob)]
        self.sid = self._current_sid()

    def _current_sid(self):
        token = w.HANDLE()
        text = ctypes.c_void_p()
        try:
            if not self.advapi.OpenProcessToken(self.kernel.GetCurrentProcess(), 8, ctypes.byref(token)):
                raise ValueError('TOKEN_UNAVAILABLE')
            size = w.DWORD()
            self.advapi.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
            buffer = ctypes.create_string_buffer(size.value)
            if not self.advapi.GetTokenInformation(token,1,buffer,size,ctypes.byref(size)):
                raise ValueError('TOKEN_UNAVAILABLE')
            sid = ctypes.cast(buffer,ctypes.POINTER(ctypes.c_void_p))[0]
            if not self.advapi.ConvertSidToStringSidW(sid,ctypes.byref(text)):
                raise ValueError('SID_UNAVAILABLE')
            return ctypes.wstring_at(text)
        finally:
            if text.value:self.kernel.LocalFree(text)
            if token.value:self.kernel.CloseHandle(token)

    def create_private_directory(self, path):
        path = Path(path).absolute()
        # Reject junctions/symlinks along the entire existing parent chain.
        for parent in path.parents:
            if parent.is_symlink() or parent.is_junction():
                raise ValueError('REPARSE_POINT_FORBIDDEN')
        descriptor = ctypes.c_void_p()
        try:
            # Protected DACL: only current token's SID gets full control, inherited by children.
            sddl = 'D:P(A;OICI;FA;;;'+self.sid+')'
            if not self.advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl,1,ctypes.byref(descriptor),None):
                raise ValueError('ACL_FAILED')
            sa = SecurityAttributes(ctypes.sizeof(SecurityAttributes),descriptor,False)
            if not self.kernel.CreateDirectoryW(str(path),ctypes.byref(sa)):
                raise ValueError('DESTINATION_EXISTS_OR_UNAVAILABLE')
        finally:
            if descriptor.value:self.kernel.LocalFree(descriptor)

    def protect(self, data):
        buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        incoming = Blob(len(data),buffer)
        outgoing = Blob()
        try:
            # No LOCAL_MACHINE flag: protection is tied to the current Windows user.
            if not self.crypt.CryptProtectData(ctypes.byref(incoming),'D6 existing L2',None,None,None,1,ctypes.byref(outgoing)):
                raise ValueError('DPAPI_FAILED')
            return ctypes.string_at(outgoing.data,outgoing.size)
        finally:
            ctypes.memset(buffer,0,len(data))
            if outgoing.data:self.kernel.LocalFree(outgoing.data)

    def publish(self, src, dst):
        # Same directory/volume. WRITE_THROUGH, no REPLACE_EXISTING and no COPY_ALLOWED.
        if not self.kernel.MoveFileExW(str(src),str(dst),8):
            raise ValueError('ATOMIC_PUBLICATION_FAILED')


def storage_directory(repository):
    local = os.environ.get('LOCALAPPDATA')
    if not local or not Path(local).is_absolute():
        raise ValueError('LOCAL_STORAGE_UNAVAILABLE')
    parent = Path(local).resolve(strict=True)
    destination = parent / 'PolymarketD6L2'
    repository = Path(repository).resolve(strict=True)
    if destination.is_relative_to(repository) or any((p/'.git').exists() for p in (parent,*parent.parents)):
        raise ValueError('STORAGE_MUST_BE_OUTSIDE_GIT')
    return destination
