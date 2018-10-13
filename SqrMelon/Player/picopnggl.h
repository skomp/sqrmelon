#pragma once
#include "settings.h"
#ifdef SUPPORT_PNG
void loadTextureFile(unsigned int& t, const char* filename
#ifdef _DEBUG
	, HWND window
#endif
);
#endif
