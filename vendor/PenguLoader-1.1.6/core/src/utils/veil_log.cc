#include "pengu.h"
#include "veil_log.h"
#include <stdarg.h>

#if OS_WIN

// core.log moves to core.log.old once it's over this size, at a process's first line
static const LONGLONG max_log_size = 1024 * 1024;

static std::wstring log_path()
{
    wchar_t dir[2048];
    DWORD length = GetEnvironmentVariableW(L"LOCALAPPDATA", dir, ARRAYSIZE(dir));
    if (length == 0 || length >= ARRAYSIZE(dir))
        return L"";
    return std::wstring(dir, length) + L"\\VeilApp\\core.log";
}

static void rotate_if_large(const std::wstring &path)
{
    WIN32_FILE_ATTRIBUTE_DATA data;
    if (!GetFileAttributesExW(path.c_str(), GetFileExInfoStandard, &data))
        return;

    LARGE_INTEGER size;
    size.LowPart = data.nFileSizeLow;
    size.HighPart = (LONG)data.nFileSizeHigh;
    if (size.QuadPart > max_log_size)
        MoveFileExW(path.c_str(), (path + L".old").c_str(), MOVEFILE_REPLACE_EXISTING);
}

void veil_log(const wchar_t *fmt, ...)
{
    static std::atomic<bool> rotated{ false };

    std::wstring path = log_path();
    if (path.empty())
        return;
    if (!rotated.exchange(true))
        rotate_if_large(path);

    wchar_t message[2048];
    va_list args;
    va_start(args, fmt);
    int length = _vsnwprintf_s(message, _TRUNCATE, fmt, args);
    va_end(args);
    if (length < 0)
        length = (int)wcslen(message);

    SYSTEMTIME now;
    GetLocalTime(&now);
    wchar_t line[2200];
    int line_length = swprintf_s(line, L"%04u-%02u-%02u %02u:%02u:%02u [%lu] %.*s\r\n",
        now.wYear, now.wMonth, now.wDay, now.wHour, now.wMinute, now.wSecond,
        GetCurrentProcessId(), length, message);
    if (line_length <= 0)
        return;

    // UTF-8, so paths with non-ASCII characters read back as written
    int size = WideCharToMultiByte(CP_UTF8, 0, line, line_length, nullptr, 0, nullptr, nullptr);
    if (size <= 0)
        return;
    std::string utf8(size, '\0');
    WideCharToMultiByte(CP_UTF8, 0, line, line_length, utf8.data(), size, nullptr, nullptr);

    // Every League process loads core.dll: append, and let the others write too
    HANDLE file = CreateFileW(path.c_str(), FILE_APPEND_DATA, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
        nullptr, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (file == INVALID_HANDLE_VALUE)
        return;
    DWORD written;
    WriteFile(file, utf8.data(), (DWORD)utf8.size(), &written, nullptr);
    CloseHandle(file);
}

#else

void veil_log(const wchar_t *, ...) {}

#endif
