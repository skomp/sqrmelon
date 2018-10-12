#include "picopnggl.h"
#ifdef SUPPORT_PNG
#include <windows.h>
#include <gl/GL.h>

void loadTextureFile(unsigned int& t, const char* filename
#ifdef DEBUG
	, HWND window
#endif
)
{
	unsigned long w, h;

	std::vector<unsigned char> buffer, image, flipped;
	loadFile(buffer, filename);
	int error = decodePNG(image, w, h, buffer.empty() ? 0 : &buffer[0], (unsigned long)buffer.size());
#ifdef DEBUG
	if (error != 0)
	{
		MessageBox(window, filename, "Error loading PNG", MB_OK);
		ExitProcess(0);
	}
#endif

	// flip vertically
	flipped.resize(image.size());
	for (unsigned long y = 0; y < h; ++y)
		CopyMemory(&flipped[(h - y - 1) * w * 4], &image[y * w * 4], w * 4);

	glBindTexture(GL_TEXTURE_2D, t);
	glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, w, h, 0, GL_RGBA, GL_UNSIGNED_BYTE, &flipped[0]);
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
	//glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP);
	//glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP);
}
#endif