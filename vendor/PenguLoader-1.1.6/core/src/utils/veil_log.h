#pragma once

// Veil: appends a timestamped line to %LOCALAPPDATA%\VeilApp\core.log. Never throws;
// a line that can't be written is dropped.
void veil_log(const wchar_t *fmt, ...);
