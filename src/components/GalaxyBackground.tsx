import { useEffect, useRef } from "react";

export function GalaxyBackground() {
  const ref = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let raf = 0;
    let w = 0;
    let h = 0;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);

    const stars = Array.from({ length: 90 }, () => ({
      x: Math.random(),
      y: Math.random(),
      r: Math.random() * 1.4 + 0.3,
      p: Math.random() * Math.PI * 2,
    }));

    const resize = () => {
      w = canvas.clientWidth;
      h = canvas.clientHeight;
      canvas.width = w * dpr;
      canvas.height = h * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    window.addEventListener("resize", resize);

    const draw = (t: number) => {
      const time = t / 1000;
      ctx.clearRect(0, 0, w, h);

      // stars
      for (const s of stars) {
        const a = 0.25 + 0.55 * Math.abs(Math.sin(time * 0.8 + s.p));
        ctx.beginPath();
        ctx.fillStyle = `rgba(190, 220, 255, ${a})`;
        ctx.arc(s.x * w, s.y * h, s.r, 0, Math.PI * 2);
        ctx.fill();
      }

      // galaxy orb
      const ox = w * 0.5 + Math.sin(time * 0.25) * w * 0.08;
      const oy = h * 0.22 + Math.cos(time * 0.2) * 18;
      const rad = Math.max(w, h) * 0.38;
      const orb = ctx.createRadialGradient(ox, oy, 0, ox, oy, rad);
      orb.addColorStop(0, "rgba(127, 182, 255, 0.30)");
      orb.addColorStop(0.4, "rgba(74, 143, 255, 0.14)");
      orb.addColorStop(1, "rgba(10, 18, 41, 0)");
      ctx.fillStyle = orb;
      ctx.beginPath();
      ctx.arc(ox, oy, rad, 0, Math.PI * 2);
      ctx.fill();

      // waves
      for (let i = 0; i < 3; i++) {
        ctx.beginPath();
        const baseY = h * (0.72 + i * 0.07);
        ctx.moveTo(0, baseY);
        for (let x = 0; x <= w; x += 8) {
          const y =
            baseY +
            Math.sin(x / (110 + i * 40) + time * (0.6 + i * 0.25)) * (14 + i * 8) +
            Math.sin(x / 45 + time * 0.9) * 3;
          ctx.lineTo(x, y);
        }
        ctx.lineTo(w, h);
        ctx.lineTo(0, h);
        ctx.closePath();
        ctx.fillStyle = `rgba(74, 143, 255, ${0.05 + i * 0.03})`;
        ctx.fill();
      }

      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
    };
  }, []);

  return (
    <div className="pointer-events-none fixed inset-0 -z-10 bg-galaxy">
      <canvas ref={ref} className="h-full w-full" />
    </div>
  );
}
