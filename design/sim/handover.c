/* Time-domain model of two adjacent sink channels crossing a blend band.
 * Build: gcc -O2 -o handover handover.c -lm
 * Usage: ./handover <band 1|2|3> <fade_s full range> <primed 0|1> <Cc_nF> <dir up=1/down=-1> [vth]
 * Prints: worst deviation of the summed sink current from the smooth target inside the band window,
 *         and from the 4 kHz staircase actually commanded.
 * Model per channel: integrator op-amp (tau = R_IN*C_C, output clamped 0..4.9 V), EKV MOSFET,
 * Kelvin shunt, zero bias current I_b = (0.4545 V - V+)/1.82 Mohm into -IN, divider RC 9.2 us on V+.
 * LED/cathode dynamics are ignored: the sum of sink currents is what the LED eventually carries.
 */
#include <stdio.h>
#include <stdlib.h>
#include <math.h>

#define VT 0.02585
typedef struct { double K, n, vth, rs, tau, vo, vp, id; } ch_t;

static double ekv(const ch_t *c, double vgs) {
    double is = 2.0 * c->n * c->n * VT * VT * c->K;
    double x = (vgs - c->vth) / (2.0 * c->n * VT);
    double l = (x > 40.0) ? x : log1p(exp(x));
    return is * l * l;
}
static double ekv_d(const ch_t *c, double vgs) {
    double is = 2.0 * c->n * c->n * VT * VT * c->K;
    double x = (vgs - c->vth) / (2.0 * c->n * VT);
    double l = (x > 40.0) ? x : log1p(exp(x));
    double s = 1.0 / (1.0 + exp(-x));
    return is * 2.0 * l * s / (2.0 * c->n * VT);
}
static const double RIN = 1000.0, RB = 1.82e6, VB = 5.0 / 11.0;
static double TDIV = 923.0 * 10e-9;
static double ib_of(double vp) { return (VB - vp) / RB; }
/* solve id = f(vo - (id+ib)*rs) */
static double solve_id(ch_t *c) {
    double ib = ib_of(c->vp), id = c->id > 0 ? c->id : 0;
    for (int k = 0; k < 30; k++) {
        double vgs = c->vo - (id + ib) * c->rs;
        double g = id - ekv(c, vgs);
        double dg = 1.0 + ekv_d(c, vgs) * c->rs;
        double nid = id - g / dg;
        if (nid < 0) nid = 0.5 * id;
        if (fabs(nid - id) < 1e-15 + 1e-10 * id) { id = nid; break; }
        id = nid;
    }
    c->id = id;
    return id;
}
/* steady-state V+ that gives drain current id */
static double vp_for(const ch_t *c, double id) {
    double vp = id * c->rs;
    for (int k = 0; k < 20; k++) vp = (id + ib_of(vp)) * c->rs + ib_of(vp) * RIN;
    return vp;
}
static double vp_dead(void) { return 0.0; }

int main(int argc, char **argv) {
    if (getenv("CDIV_NF")) TDIV = 923.0 * atof(getenv("CDIV_NF")) * 1e-9;
    int band = atoi(argv[1]);
    double T = atof(argv[2]);
    int primed = atoi(argv[3]);
    double cc = atof(argv[4]) * 1e-9;
    int dir = atoi(argv[5]);
    double vth_lo = argc > 6 ? atof(argv[6]) : 2.0;
    const double IMIN = 5e-6, IMAX = 1.4, DEC = log10(IMAX / IMIN);
    const double LSB = 2.5 / 13.0 / 65536.0, EKA = 25e-6, FUPD = 4000.0;
    double lo, hi;
    ch_t L = {0}, H = {0};
    if (band == 1) { lo = 1.4e-3; hi = 1.6e-3; L = (ch_t){0.3, 1.5, vth_lo, 100.0}; H = (ch_t){0.3, 1.5, vth_lo, 10.0}; }
    else if (band == 2) { lo = 14e-3; hi = 16e-3; L = (ch_t){0.3, 1.5, vth_lo, 10.0}; H = (ch_t){0.5, 1.5, vth_lo, 1.0}; }
    else { lo = 140e-3; hi = 160e-3; L = (ch_t){0.5, 1.5, vth_lo, 1.0}; H = (ch_t){6.125, 1.6, vth_lo - 0.3, 0.1}; }
    L.tau = RIN * cc; H.tau = RIN * cc;
    double kaL = EKA / L.rs, kaH = EKA / H.rs;          /* keep-alive currents */
    /* window: from 0.1 decade below lo to 0.1 decade above hi */
    double b0 = log10(lo / IMIN) / DEC - 0.10 / DEC, b1 = log10(hi / IMIN) / DEC + 0.10 / DEC;
    double rate = 1.0 / T;                               /* b per second */
    double tw = (b1 - b0) / rate;
    double dt = 2e-8;
    /* limit dt for speed on long runs: loop time constant >= ~1 us */
    if (tw > 0.2) dt = 1e-7;
    long nsteps = (long)(tw / dt);
    long nupd = (long)(1.0 / (FUPD * dt));
    double tgt_step = 0, worst_s = 0, worst_q = 0, t_worst = 0, lp = 0, worst_lp = 0; int lp_init = 0;
    /* initial state: settle at the start level */
    double bstart = dir > 0 ? b0 : b1;
    double I0 = IMIN * pow(10.0, bstart * DEC);
    /* shares */
    /* blend: linear (mode 0) or log-ratio (mode 1).  Log-ratio: ln(sH/sL) runs linearly in log(I)
       from ln(kaH/(lo-kaH)) at lo to ln((hi-kaL)/kaL) at hi, so each channel's share grows
       exponentially from its keep-alive and the subthreshold loop can follow it. */
    int mode = getenv("BLEND") ? atoi(getenv("BLEND")) : 1;
    double r0 = log(kaH / (lo - kaH)), r1 = log((hi - kaL) / kaL);
    #define SPLIT(I, sL, sH) do { double u = (log(I) - log(lo)) / (log(hi) - log(lo)); \
        if (mode == 1) { if (u <= 0) { sH = primed ? kaH : 0; sL = (I) - sH; } \
                         else if (u >= 1) { sL = kaL; sH = (I) - kaL; } \
                         else { double r = exp(r0 + (r1 - r0) * u); sH = (I) * r / (1 + r); sL = (I) / (1 + r); } } \
        else { double w = ((I) - lo) / (hi - lo); if (w < 0) w = 0; if (w > 1) w = 1; \
        sH = (I) * w; if (primed && sH < kaH) sH = kaH; sL = (I) - sH; if (sL < kaL) { sL = kaL; sH = (I) - kaL; } \
        if (!primed && w <= 0) { sH = 0; sL = (I); } } } while (0)
    double sL, sH;
    SPLIT(I0, sL, sH);
    L.vp = floor(vp_for(&L, sL) / LSB) * LSB; H.vp = (sH > 0) ? floor(vp_for(&H, sH) / LSB) * LSB : vp_dead();
    /* settle: find vo giving sL, sH */
    for (int pass = 0; pass < 2; pass++) {
        ch_t *c = pass ? &H : &L; double s = pass ? sH : sL;
        if (s <= 0) { c->vo = 0; c->id = 0; continue; }
        double a = 0, bb = 4.9;
        for (int k = 0; k < 200; k++) { c->vo = 0.5 * (a + bb); c->id = 0; double id = solve_id(c);
            double tgt = (c->vp - ib_of(c->vp) * RIN) / c->rs - ib_of(c->vp);
            if (id > tgt) bb = c->vo; else a = c->vo; }
    }
    double vpL_cmd = L.vp, vpH_cmd = H.vp;
    for (long i = 0; i <= nsteps; i++) {
        double t = i * dt;
        if (i % nupd == 0) {
            double b = dir > 0 ? b0 + rate * t : b1 - rate * t;
            tgt_step = IMIN * pow(10.0, b * DEC);
            SPLIT(tgt_step, sL, sH);
            vpL_cmd = floor(vp_for(&L, sL) / LSB + 0.5) * LSB;
            vpH_cmd = (sH > 0) ? floor(vp_for(&H, sH) / LSB + 0.5) * LSB : vp_dead();
        }
        /* divider RC */
        L.vp += (vpL_cmd - L.vp) * dt / TDIV; H.vp += (vpH_cmd - H.vp) * dt / TDIV;
        for (int pass = 0; pass < 2; pass++) {
            ch_t *c = pass ? &H : &L;
            double id = solve_id(c);
            double vs = (id + ib_of(c->vp)) * c->rs;
            double dv = (c->vp - vs - ib_of(c->vp) * RIN) / c->tau;
            c->vo += dv * dt;
            if (c->vo < 0) c->vo = 0;
            if (c->vo > 4.9) c->vo = 4.9;
        }
        double itot = L.id + H.id;
        double b = dir > 0 ? b0 + rate * t : b1 - rate * t;
        double smooth = IMIN * pow(10.0, b * DEC);
        double es = itot / smooth - 1.0, eq = itot / tgt_step - 1.0;
        if (!lp_init) { lp = es; lp_init = 1; } else lp += (es - lp) * dt / 1e-3;
        if (t > 2.0 / FUPD) {   /* skip the first two updates */
            if (fabs(lp) > fabs(worst_lp)) worst_lp = lp;
            if (fabs(es) > fabs(worst_s)) { worst_s = es; t_worst = t; }
            if (fabs(eq) > fabs(worst_q)) worst_q = eq;
        }
    }
    printf("band %d  %4.0f s %s %s Cc %.1f nF Cdiv %3.0f nF: peak %+7.3f %% (vs staircase %+7.3f %%), after 1 ms low-pass %+7.3f %%\n",
           band, T, dir > 0 ? "up  " : "down", primed ? "primed  " : "unprimed", cc * 1e9, TDIV / 923.0 * 1e9, worst_s * 100, worst_q * 100, worst_lp * 100);
    return 0;
}
