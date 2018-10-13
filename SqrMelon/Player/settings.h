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

// #define AUDIO_64KLANG2
#define AUDIO_BASS
#ifdef AUDIO_BASS
#include "bass.h"
const float BPM = 100.0f;
#endif
// #define NO_AUDIO
#ifdef NO_AUDIO
#define BPM 124.0f
#define START_BEAT 0.0f
#define SPEED 1.0f
#endif

// #define SUPPORT_3D_TEXTURE
#define SUPPORT_PNG

// #define RESOLUTION_SELECTOR
// set resolution settings here if not using resolution selector
// set resolution to 0 to get screen resolution, it will force to windowed because there is no reason to change to full screen at the current resolution
#ifndef RESOLUTION_SELECTOR
#define DEMO_WIDTH 1280
#define DEMO_HEIGHT 720
#define IS_WINDOWED 1
#endif
