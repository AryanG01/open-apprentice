import { useEffect, useRef } from "react";

const SIZE = 168;

/** A small turntable of the product while Nemotron reads the banner (10 to 30 seconds). three.js is loaded only when this
 *  mounts, so the first screen never pays for it. Reduced motion gets one still frame; no WebGL gets nothing (the status
 *  chip beside it still says what is happening). The model is a stylised interpretation: docs/evaluation/headphones3d_img2threejs.md. */
export function ReadingLoader() {
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    let stop = (): void => undefined;
    let cancelled = false;
    (async () => {
      const el = canvas.current;
      if (!el) return;
      const THREE = await import("three");
      const { createHeadphones, disposeHeadphones } = await import("./headphones3d");
      if (cancelled) return;
      let renderer: InstanceType<typeof THREE.WebGLRenderer>;
      try {
        renderer = new THREE.WebGLRenderer({ canvas: el, alpha: true, antialias: true });
      } catch {
        return; // no WebGL: the chip is enough
      }
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      renderer.setSize(SIZE, SIZE, false);
      const scene = new THREE.Scene();
      const camera = new THREE.PerspectiveCamera(32, 1, 0.1, 20);
      camera.position.set(0, 0.05, 6.2);
      scene.add(new THREE.AmbientLight(0xffffff, 1.25));
      const sun = new THREE.DirectionalLight(0xffffff, 2.4);
      sun.position.set(2.5, 3, 4);
      scene.add(sun);
      const model = createHeadphones();
      scene.add(model);

      const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      let raf = 0;
      const draw = (t: number) => {
        model.rotation.y = still ? 0.6 : Math.sin(t / 1400) * 0.75; // sway, so the invented rear faces never face the viewer
        model.rotation.x = 0.08;
        renderer.render(scene, camera);
        if (!still && !document.hidden) raf = requestAnimationFrame(draw);
      };
      const resume = () => {
        if (!still && !document.hidden) raf = requestAnimationFrame(draw);
      };
      draw(0);
      document.addEventListener("visibilitychange", resume);
      stop = () => {
        cancelAnimationFrame(raf);
        document.removeEventListener("visibilitychange", resume);
        scene.remove(model);
        disposeHeadphones(model);
        renderer.dispose();
      };
    })().catch(() => undefined);
    return () => {
      cancelled = true;
      stop();
    };
  }, []);

  return <canvas ref={canvas} className="reading-canvas" width={SIZE} height={SIZE} aria-hidden="true" />;
}
