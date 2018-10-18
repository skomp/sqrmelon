void main()
{
    outColor0=vec4(perlin(gl_FragCoord.xy/uResolution,8.0,15,2.0,0.5),
        perlin(gl_FragCoord.xy/uResolution + perlin(gl_FragCoord.xy/uResolution,2.0,15,2.0,0.5),4.0,3,2.0,0.5),
        perlin(perlin(gl_FragCoord.xy/uResolution,2.0,13,2.0,0.5)*6.0,7,2.0,0.5),
        sqrt(billows(gl_FragCoord.xy/uResolution,8.0,15,2.0,0.5)));
}
