"use client";

import { useEffect, useRef } from "react";
import * as THREE from "three";

const MODE_COLORS: Record<string, string> = {
  JARVIS:   "#38e8ff",
  FRIDAY:   "#ffd166",
  VERONICA: "#b284ff",
  SENTINEL: "#ff5f6d",
};

type ArcCoreProps = {
  mode?: string;
  isThinking?: boolean;
  isListening?: boolean;
};

export function ArcCore({ mode = "JARVIS", isThinking = false, isListening = false }: ArcCoreProps) {
  const mountRef       = useRef<HTMLDivElement>(null);
  const coreMaterialRef = useRef<THREE.MeshStandardMaterial | null>(null);
  const ringMaterialRef = useRef<THREE.MeshStandardMaterial | null>(null);
  const lightRef        = useRef<THREE.PointLight | null>(null);
  const speedRef        = useRef(1);
  const listeningRef    = useRef(false);
  const thinkingRef     = useRef(false);

  useEffect(() => {
    speedRef.current   = isThinking ? 3 : isListening ? 1.5 : 1;
    listeningRef.current = isListening;
    thinkingRef.current  = isThinking;
  }, [isThinking, isListening]);

  useEffect(() => {
    const modeKey = mode.toUpperCase();
    const color = MODE_COLORS[modeKey] ?? MODE_COLORS.JARVIS;
    if (coreMaterialRef.current) {
      coreMaterialRef.current.color.set(color);
      coreMaterialRef.current.emissive.set(color);
    }
    if (ringMaterialRef.current) {
      ringMaterialRef.current.color.set(color);
      ringMaterialRef.current.emissive.set(color);
    }
    if (lightRef.current) {
      lightRef.current.color.set(color);
    }
  }, [mode]);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;

    const modeKey = mode.toUpperCase();
    const initialColor = MODE_COLORS[modeKey] ?? MODE_COLORS.JARVIS;
    const reducedMotion =
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const scene  = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(52, mount.clientWidth / mount.clientHeight, 0.1, 100);
    camera.position.z = 5;

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(mount.clientWidth, mount.clientHeight);
    mount.appendChild(renderer.domElement);

    const group = new THREE.Group();
    scene.add(group);

    const coreGeometry = new THREE.IcosahedronGeometry(1.05, 2);
    const coreMaterial = new THREE.MeshStandardMaterial({
      color:            initialColor,
      emissive:         initialColor,
      emissiveIntensity: 1.8,
      wireframe:        true,
    });
    coreMaterialRef.current = coreMaterial;
    const core = new THREE.Mesh(coreGeometry, coreMaterial);
    group.add(core);

    const ringGeometry = new THREE.TorusGeometry(1.6, 0.025, 12, 96);
    const ringMaterial = new THREE.MeshStandardMaterial({
      color:            initialColor,
      emissive:         initialColor,
      emissiveIntensity: 1.35,
    });
    ringMaterialRef.current = ringMaterial;
    const ring = new THREE.Mesh(ringGeometry, ringMaterial);
    group.add(ring);

    const outerGeometry = new THREE.TorusGeometry(2.1, 0.015, 12, 128);
    const outerMaterial = new THREE.MeshStandardMaterial({
      color:            "#94a3b8",
      emissive:         "#94a3b8",
      emissiveIntensity: 0.8,
    });
    const outerRing = new THREE.Mesh(outerGeometry, outerMaterial);
    outerRing.rotation.x = Math.PI / 2;
    group.add(outerRing);

    scene.add(new THREE.AmbientLight("#ffffff", 0.4));

    const point = new THREE.PointLight(initialColor, 18, 10);
    point.position.set(0, 0, 3);
    lightRef.current = point;
    scene.add(point);

    let frameId = 0;
    let clock = 0;

    const handleResize = () => {
      if (!mount) return;
      camera.aspect = mount.clientWidth / mount.clientHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(mount.clientWidth, mount.clientHeight);
    };

    const animate = () => {
      frameId = window.requestAnimationFrame(animate);
      if (!reducedMotion) {
        const speed = speedRef.current;
        clock += 0.016 * speed;

        core.rotation.y  += 0.008 * speed;
        core.rotation.x  += 0.004 * speed;
        ring.rotation.z  += 0.010 * speed;
        outerRing.rotation.z -= 0.006 * speed;

        // Pulse opacity when listening
        if (listeningRef.current && coreMaterial) {
          const pulse = 0.6 + 0.4 * Math.abs(Math.sin(clock * 2.5));
          coreMaterial.opacity  = pulse;
          coreMaterial.transparent = true;
          ringMaterial.opacity  = pulse;
          ringMaterial.transparent = true;
        } else {
          coreMaterial.opacity = 1;
          coreMaterial.transparent = false;
          ringMaterial.opacity = 1;
          ringMaterial.transparent = false;
        }
      }
      renderer.render(scene, camera);
    };

    animate();
    window.addEventListener("resize", handleResize);

    return () => {
      window.cancelAnimationFrame(frameId);
      window.removeEventListener("resize", handleResize);
      coreGeometry.dispose();
      coreMaterial.dispose();
      ringGeometry.dispose();
      ringMaterial.dispose();
      outerGeometry.dispose();
      outerMaterial.dispose();
      renderer.dispose();
      coreMaterialRef.current = null;
      ringMaterialRef.current = null;
      lightRef.current        = null;
      if (mount.contains(renderer.domElement)) mount.removeChild(renderer.domElement);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return <div ref={mountRef} className="h-[320px] w-full" />;
}
