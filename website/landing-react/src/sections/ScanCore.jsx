import { useRef, useMemo, useState, useEffect } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { Sparkles } from "@react-three/drei";

/* The hero's 3D backdrop — owner sent real reference footage of current Awwwards-style Three.js
   product-showcase sites and asked for that tier of spectacle specifically ("spaceship-level"),
   not just CSS/Framer Motion polish. There's no literal product to render in 3D here, so instead
   of forcing one, this renders something that actually represents what the product DOES: a
   glowing wireframe "core" under constant rotation (the market being scanned) ringed by two tilted
   orbits (the scan sweep) with a drifting field of small glowing points (listings turning up) —
   real-time scanning made visual, in the brand's own teal/gold, not a generic sci-fi prop.
   Deliberately a dark, self-contained "viewport" (its own background, not the page's) so it reads
   consistently in both light and dark site themes rather than needing every material re-tuned per
   theme — the same reason the reference sites' own 3D scenes always sat inside a dark device
   frame regardless of the page around them. The dark panel/frame itself lives one level up, in
   Hero.jsx's .tl-scancore-shell — this component (lazy-loaded, see Hero.jsx's own comment on why)
   only ever needs to fill that shell, never define it, so the shell's own background already
   shows correctly the instant before this chunk finishes loading. */

function Core() {
  const group = useRef(null);
  const inner = useRef(null);
  const ringA = useRef(null);
  const ringB = useRef(null);
  const pointer = useRef({ x: 0, y: 0 });

  useEffect(() => {
    function onMove(e) {
      const x = (e.clientX / window.innerWidth) * 2 - 1;
      const y = (e.clientY / window.innerHeight) * 2 - 1;
      pointer.current.x = x;
      pointer.current.y = y;
    }
    window.addEventListener("pointermove", onMove, { passive: true });
    return () => window.removeEventListener("pointermove", onMove);
  }, []);

  useFrame((state, delta) => {
    if (inner.current) {
      inner.current.rotation.y += delta * 0.18;
      inner.current.rotation.x += delta * 0.06;
    }
    if (ringA.current) ringA.current.rotation.z += delta * 0.12;
    if (ringB.current) ringB.current.rotation.z -= delta * 0.09;
    if (group.current) {
      // Bounded pointer-parallax on the whole assembly, not a free orbit — a controlled drift,
      // same restraint as Hero.jsx's own TiltImage (a spring toward a small target offset, not a
      // 1:1 cursor follow), so it reads as alive without ever feeling like a draggable toy.
      const targetY = pointer.current.x * 0.25;
      const targetX = pointer.current.y * 0.15;
      group.current.rotation.y += (targetY - group.current.rotation.y) * Math.min(1, delta * 2);
      group.current.rotation.x += (targetX - group.current.rotation.x) * Math.min(1, delta * 2);
    }
  });

  return (
    <group ref={group}>
      <mesh ref={inner}>
        <icosahedronGeometry args={[1.15, 1]} />
        <meshStandardMaterial
          color="#0e8a82"
          emissive="#0e8a82"
          emissiveIntensity={1.4}
          wireframe
          toneMapped={false}
        />
      </mesh>
      <mesh ref={ringA} rotation={[Math.PI / 2.4, 0, 0]}>
        <torusGeometry args={[1.9, 0.012, 8, 128]} />
        <meshStandardMaterial color="#d9a441" emissive="#d9a441" emissiveIntensity={2} toneMapped={false} />
      </mesh>
      <mesh ref={ringB} rotation={[Math.PI / 1.7, Math.PI / 5, 0]}>
        <torusGeometry args={[2.35, 0.008, 8, 128]} />
        <meshStandardMaterial color="#ecc978" emissive="#ecc978" emissiveIntensity={1.6} toneMapped={false} />
      </mesh>
    </group>
  );
}

// This is a client-only bundle (mounted via ReactDOM.createRoot, no SSR), so window/document are
// always available here — computed once via useState's lazy initializer rather than an effect,
// since the check never needs to re-run after mount and doing it in an effect would just cost an
// extra, unnecessary render.
function supportsScene() {
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduceMotion) return false;
  // WebGL support check — Canvas would otherwise throw past this component's own render and take
  // the whole page down with it; skip mounting entirely rather than risk that, same fail-safe
  // reasoning as the reduced-motion check just above. Leaves the shell's own static dark panel
  // visible, exactly like the pre-chunk-load state.
  try {
    const c = document.createElement("canvas");
    return !!(c.getContext("webgl2") || c.getContext("webgl"));
  } catch {
    return false;
  }
}

export default function ScanCore() {
  const [enabled] = useState(supportsScene);
  const camera = useMemo(() => ({ position: [0, 0, 6], fov: 45 }), []);

  if (!enabled) return null;

  return (
    <Canvas dpr={[1, 1.75]} camera={camera} gl={{ antialias: true, alpha: false }} style={{ position: "absolute", inset: 0 }}>
      <color attach="background" args={["#0b1a19"]} />
      <fog attach="fog" args={["#0b1a19", 6, 11]} />
      <ambientLight intensity={0.35} />
      <pointLight position={[3, 2, 4]} intensity={40} color="#0e8a82" />
      <pointLight position={[-3, -2, 3]} intensity={30} color="#d9a441" />
      <Core />
      <Sparkles count={70} scale={[7, 5, 5]} size={2.4} speed={0.25} color="#ecc978" opacity={0.7} />
    </Canvas>
  );
}
