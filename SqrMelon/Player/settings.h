#pragma once

#define _CRT_SECURE_NO_WARNINGS
#define WIN32_LEAN_AND_MEAN
#define VC_EXTRALEAN

#include "wglext.h"

#ifndef DEMO
	#include <assert.h>
#else
	#define assert(IGNORED)
#endif

#pragma comment(lib, "opengl32.lib")

// #define NO_AUDIO
// #define AUDIO_64KLANG2
#define AUDIO_BASS

// #define SUPPORT_3D_TEXTURE
#define SUPPORT_PNG
