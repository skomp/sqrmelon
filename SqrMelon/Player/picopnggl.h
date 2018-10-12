#pragma once
#include "picopng.h"
#ifdef SUPPORT_PNG
void loadTextureFile(unsigned int& t, const char* filename
#ifdef DEBUG
	, HWND window
#endif
);
#endif