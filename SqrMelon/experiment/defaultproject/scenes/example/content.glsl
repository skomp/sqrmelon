vec3 FogColor(Ray ray, float fog)
{
    return mix(vec3(1.0), vec3(0.2), smoothstep(-0.2, 0.2, ray.direction.y));
}
uniform float uEmissiveShapeActivate;
float fEmissive(vec3 p, out vec4 m)
{
    m = vec4(0, 0, 0, -1);
    if(uEmissiveShapeActivate == 0.0)
        return FAR;
    m.xyz = vec3(1.0, 0.5, 0.1) * uEmissiveShapeActivate;
    return fSphere(p, 1.0);
}
float fEmissive(vec3 p) { vec4 m; return fEmissive(p, m); }

float fField(vec3 p, out vec4 m)
{
    vec4 im;
    vec3 op=p;
    float ir, r = fEmissive(p, m);

    ir = p.y + 1.0;
    fOpUnion(r,ir,m,vec4(p,0));

    pModPolar(p.xz, 8.0);
    p.x -= 1.5;
    ir = fSphere(p, 0.25);
    fOpUnion(r,ir,m,vec4(p,1));

    return r;
}

/*
vec3 albedo
vec3 additive
float specularity
float roughness
float reflectivity
float blur
float metallicity
*/
Material GetMaterial(Hit hit)
{
    int objectId = int(hit.materialId.w);
    if(objectId==-1) // emissive material
        return Material(vec3(0.0), vec3(hit.materialId.xyz), 0.0, 0.0, 0.0, 0.0, 0.0);
    return Material(vec3(0.5), vec3(0.0), 0.0, 0.0, 0.0, 0.0, 0.0);
}

vec3 Lighting(LightData data)
{
    vec3 result = vec3(0);
    result += DirectionalLight(data, vec3(0.5, 1.0, 1.0), vec3(1.0), shadowArgs());

    // Emissive light
    IMPL_EMISSIVE_LIGHT(result, fEmissive);

    return result;
}

vec3 Normal(inout Hit hit)
{
    const vec2 e=vec2(EPSILON+EPSILON,0.0);
    vec3 point=hit.point;
    vec4 taps = vec4(fField(point+e.xyy),fField(point+e.yxy),fField(point+e.yyx),fField(point));
    return  normalize(taps.xyz-taps.w);
}
