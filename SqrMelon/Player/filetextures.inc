#include "settings.h"

#ifdef SUPPORT_PNG

#include <windows.h>

#ifndef _DEBUG
#define LODEPNG_NO_COMPILE_ERROR_TEXT
#endif

#include "lodepng.h"

void loadTextureFile(unsigned int& t, const char* filename
#ifdef _DEBUG
, HWND window
#endif
)
{
	unsigned error;
	unsigned char* image;
	size_t width, height;
	error = lodepng_decode_file(&image, &width, &height, filename, LCT_RGBA, 8);

	#ifdef _DEBUG
	if (error != 0)
	{
		MessageBox(window, filename, "Error loading PNG", MB_OK);
		MessageBox(window, lodepng_error_text(error), "Error loading PNG", MB_OK);
		ExitProcess(0);
	}
	#endif

	// flip vertically
	//unsigned char* flipped = (unsigned char*)HeapAlloc(GetProcessHeap(), 0, width * height * 4);
	//for (size_t y = 0; y < height; ++y)
	//	CopyMemory(&flipped[(height - y - 1) * width * 4], &image[y * width * 4], width * 4);

	glBindTexture(GL_TEXTURE_2D, t);
	glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, width, height, 0, GL_RGBA, GL_UNSIGNED_BYTE, &image[0]);
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
	//glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP);
	//glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP);
}

#endif
