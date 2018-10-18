// This pass is applied before any other post effects like DoF and bloom. Add 2D, composite raytraced elements, etc.
// Notice that alpha is "intersection to camera distance", for depth of field. Return uSharpDist for pixels that should not be blurred.

void main()
{
    outColor0 = texelFetch(uImages[0], ivec2(gl_FragCoord.xy),0);
    PreFxOverlay(outColor0);
}
