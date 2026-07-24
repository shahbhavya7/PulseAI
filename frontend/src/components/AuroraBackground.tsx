/**
 * Fixed, full-viewport animated backdrop the whole app floats over. This is what
 * makes the glass read: `backdrop-filter: blur()` needs *moving colour* behind
 * it, not a flat fill.
 *
 * Critical stacking rules (this was the bug before):
 *   - NO opaque background on this layer — it must let the blobs show. The base
 *     near-black lives on <html>, painted once, behind everything.
 *   - z-0 (not -z-10). A negative z-index would render behind the page's own
 *     background canvas and be covered. Content sits above via the app shell's
 *     relative/z-10 wrapper.
 *   - pointer-events: none so it never blocks the UI.
 */
export function AuroraBackground() {
  return (
    <div
      aria-hidden
      className="pointer-events-none fixed inset-0 z-0 overflow-hidden"
    >
      {/* Big, saturated, continuously drifting colour blobs. */}
      <div className="absolute -left-40 -top-40 h-[46rem] w-[46rem] rounded-full bg-[#04f0f0]/30 blur-[130px] animate-aurora-1" />
      <div className="absolute -bottom-52 right-[-14rem] h-[42rem] w-[42rem] rounded-full bg-[#b57bff]/28 blur-[130px] animate-aurora-2" />
      <div className="absolute left-1/3 top-1/4 h-[34rem] w-[34rem] rounded-full bg-[#3b82f6]/22 blur-[120px] animate-aurora-3" />
      <div className="absolute bottom-1/4 left-[-8rem] h-[28rem] w-[28rem] rounded-full bg-[#22e39a]/16 blur-[120px] animate-aurora-1" />

      {/* Fine dot grid for texture/depth. */}
      <div
        className="absolute inset-0 opacity-[0.18]"
        style={{
          backgroundImage:
            "radial-gradient(circle at 1px 1px, hsl(0 0% 100% / 0.4) 1px, transparent 0)",
          backgroundSize: "26px 26px",
        }}
      />

      {/* Vignette so edges fall into true black and centre content stays legible. */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_75%_60%_at_50%_40%,transparent_20%,hsl(240_10%_3.5%/0.65)_100%)]" />
    </div>
  );
}
