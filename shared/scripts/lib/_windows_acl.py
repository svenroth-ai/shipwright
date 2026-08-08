"""Minimal Windows DACL inspection for the private host-lease namespace."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from pathlib import Path

from scripts.lib._windows_acl_trust import _TRUSTED_SYSTEM_SIDS, _owner_is_trusted

_SE_FILE_OBJECT = 1
_OWNER_SECURITY_INFORMATION = 0x1
_DACL_SECURITY_INFORMATION = 0x4
_TOKEN_QUERY = 0x8
_TOKEN_USER = 1
_DANGEROUS = (
    0x00000002 | 0x00000004 | 0x00000010 | 0x00000040 | 0x00000100
    | 0x00010000 | 0x00040000 | 0x00080000 | 0x10000000 | 0x40000000
)


class _ACL(ctypes.Structure):
    _fields_ = [
        ("AclRevision", wintypes.BYTE),
        ("Sbz1", wintypes.BYTE),
        ("AclSize", wintypes.WORD),
        ("AceCount", wintypes.WORD),
        ("Sbz2", wintypes.WORD),
    ]


class _ACE_HEADER(ctypes.Structure):
    _fields_ = [
        ("AceType", wintypes.BYTE),
        ("AceFlags", wintypes.BYTE),
        ("AceSize", wintypes.WORD),
    ]


class _SID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Sid", wintypes.LPVOID), ("Attributes", wintypes.DWORD)]


class _TOKEN_USER_VALUE(ctypes.Structure):
    _fields_ = [("User", _SID_AND_ATTRIBUTES)]


def _ace_type_is_supported(ace_type: int) -> bool:
    return ace_type in {0, 1}


def _apis():
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.argtypes = []
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [wintypes.LPVOID]
    kernel.LocalFree.restype = wintypes.LPVOID
    advapi.GetNamedSecurityInfoW.argtypes = [
        wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD,
        ctypes.POINTER(wintypes.LPVOID), ctypes.POINTER(wintypes.LPVOID),
        ctypes.POINTER(wintypes.LPVOID), ctypes.POINTER(wintypes.LPVOID),
        ctypes.POINTER(wintypes.LPVOID),
    ]
    advapi.GetNamedSecurityInfoW.restype = wintypes.DWORD
    advapi.GetAce.argtypes = [wintypes.LPVOID, wintypes.DWORD,
                              ctypes.POINTER(wintypes.LPVOID)]
    advapi.GetAce.restype = wintypes.BOOL
    advapi.ConvertSidToStringSidW.argtypes = [wintypes.LPVOID,
                                              ctypes.POINTER(wintypes.LPWSTR)]
    advapi.ConvertSidToStringSidW.restype = wintypes.BOOL
    advapi.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                        ctypes.POINTER(wintypes.HANDLE)]
    advapi.OpenProcessToken.restype = wintypes.BOOL
    advapi.GetTokenInformation.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi.GetTokenInformation.restype = wintypes.BOOL
    return advapi, kernel


def _sid_string(sid, advapi, kernel) -> str:
    value = wintypes.LPWSTR()
    if not advapi.ConvertSidToStringSidW(sid, ctypes.byref(value)):
        raise OSError(ctypes.get_last_error(), "ConvertSidToStringSidW failed")
    try:
        return value.value
    finally:
        kernel.LocalFree(ctypes.cast(value, wintypes.LPVOID))


def _current_sid(advapi, kernel) -> str:
    token = wintypes.HANDLE()
    if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), _TOKEN_QUERY,
                                   ctypes.byref(token)):
        raise OSError(ctypes.get_last_error(), "OpenProcessToken failed")
    try:
        needed = wintypes.DWORD()
        advapi.GetTokenInformation(token, _TOKEN_USER, None, 0, ctypes.byref(needed))
        if not needed.value:
            raise OSError(ctypes.get_last_error(), "GetTokenInformation size failed")
        data = ctypes.create_string_buffer(needed.value)
        if not advapi.GetTokenInformation(
                token, _TOKEN_USER, data, needed, ctypes.byref(needed)):
            raise OSError(ctypes.get_last_error(), "GetTokenInformation failed")
        user = ctypes.cast(data, ctypes.POINTER(_TOKEN_USER_VALUE)).contents
        return _sid_string(user.User.Sid, advapi, kernel)
    finally:
        kernel.CloseHandle(token)


def owner_sid_of(path: Path) -> str:
    """The raw owner SID string of *path*, with no trust decision applied --
    split out of path_acl_is_private() so a caller (a test, a diagnostic)
    can observe the actual owner independently of whether this module
    currently trusts it. The owner/dacl/sacl pointers GetNamedSecurityInfoW
    returns all point INTO the one ppSecurityDescriptor allocation, so that
    parameter must still be supplied (and freed) even though only the
    owner is wanted here -- mirrors path_acl_is_private's own call shape."""
    advapi, kernel = _apis()
    owner, descriptor = wintypes.LPVOID(), wintypes.LPVOID()
    code = advapi.GetNamedSecurityInfoW(
        str(path), _SE_FILE_OBJECT, _OWNER_SECURITY_INFORMATION,
        ctypes.byref(owner), None, None, None, ctypes.byref(descriptor),
    )
    if code:
        raise OSError(f"GetNamedSecurityInfoW failed with {code}")
    try:
        if not owner:
            raise OSError("owner is absent")
        return _sid_string(owner, advapi, kernel)
    finally:
        if descriptor:
            kernel.LocalFree(descriptor)


def path_acl_is_private(path: Path) -> tuple[bool, str]:
    """Require current-user ownership and no dangerous allow ACE for others."""
    advapi, kernel = _apis()
    owner, dacl, descriptor = wintypes.LPVOID(), wintypes.LPVOID(), wintypes.LPVOID()
    code = advapi.GetNamedSecurityInfoW(
        str(path), _SE_FILE_OBJECT,
        _OWNER_SECURITY_INFORMATION | _DACL_SECURITY_INFORMATION,
        ctypes.byref(owner), None, ctypes.byref(dacl), None, ctypes.byref(descriptor),
    )
    if code:
        return False, f"GetNamedSecurityInfoW failed with {code}"
    try:
        if not owner or not dacl:
            return False, "owner or DACL is absent"
        current = _current_sid(advapi, kernel)
        owner_sid = _sid_string(owner, advapi, kernel)
        if not _owner_is_trusted(owner_sid, current):
            # Names the observed owner (the actionable diagnostic value) but
            # not the current-process SID -- this string reaches a public
            # CI log via HostLeaseError, and the current SID identifies the
            # machine/domain + account RID for no diagnostic benefit the
            # owner SID doesn't already provide (Stage 3 doubt review).
            return False, (f"path is owned by {owner_sid}, which is neither "
                            f"the current user nor a trusted system principal")
        trusted = _TRUSTED_SYSTEM_SIDS | {current}
        acl = ctypes.cast(dacl, ctypes.POINTER(_ACL)).contents
        for index in range(acl.AceCount):
            ace = wintypes.LPVOID()
            if not advapi.GetAce(dacl, index, ctypes.byref(ace)):
                return False, f"GetAce failed at index {index}"
            header = ctypes.cast(ace, ctypes.POINTER(_ACE_HEADER)).contents
            if not _ace_type_is_supported(header.AceType):
                return False, f"unsupported allow ACE type {header.AceType}"
            if header.AceType == 0:
                mask = ctypes.c_uint32.from_address(ace.value + 4).value
                sid = _sid_string(wintypes.LPVOID(ace.value + 8), advapi, kernel)
                if mask & _DANGEROUS and sid not in trusted:
                    return False, f"untrusted principal {sid} has write/delete access"
        return True, ""
    except (OSError, ValueError) as exc:
        return False, str(exc)
    finally:
        if descriptor:
            kernel.LocalFree(descriptor)
