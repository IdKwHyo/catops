import { useEffect, useRef } from 'react';

type IdleWindow = Window & {
  requestIdleCallback?: (callback: IdleRequestCallback, options?: IdleRequestOptions) => number;
  cancelIdleCallback?: (handle: number) => void;
};

type NetworkAwareNavigator = Navigator & {
  connection?: { saveData?: boolean };
};

/**
 * Progressive enhancement for the editorial overview only.
 *
 * The operational views never pay for these dependencies. Motion and WebGL are
 * loaded after first paint, skipped on touch/constrained devices, and fully
 * removed when the overview unmounts.
 */
export function CinematicOverviewEffects() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const stage = canvas?.closest<HTMLElement>('.editorial-stage');
    const overview = canvas?.closest<HTMLElement>('.overview-page');
    if (!canvas || !stage || !overview) return;

    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    const finePointer = window.matchMedia('(hover: hover) and (pointer: fine)');
    const connection = (navigator as NetworkAwareNavigator).connection;
    const constrainedDevice = navigator.hardwareConcurrency <= 4 || connection?.saveData === true;

    if (reduceMotion.matches || !finePointer.matches || window.innerWidth < 760 || constrainedDevice) return;

    let cancelled = false;
    let started = false;
    let idleHandle: number | undefined;
    let timeoutHandle: number | undefined;
    const teardown: Array<() => void> = [];
    const idleWindow = window as IdleWindow;

    const boot = async () => {
      if (cancelled || started) return;
      started = true;

      try {
        const [{ default: Lenis }, { gsap }, { ScrollTrigger }] = await Promise.all([
          import('lenis'),
          import('gsap'),
          import('gsap/ScrollTrigger'),
        ]);
        if (cancelled) return;

        gsap.registerPlugin(ScrollTrigger);

        const lenis = new Lenis({
          lerp: 0.075,
          smoothWheel: true,
          syncTouch: false,
          wheelMultiplier: 0.88,
          overscroll: true,
        });
        const onLenisScroll = () => ScrollTrigger.update();
        lenis.on('scroll', onLenisScroll);
        teardown.push(() => {
          lenis.off('scroll', onLenisScroll);
          lenis.destroy();
        });

        let shaderProgress = 0;
        const motionContext = gsap.context(() => {
          const heroTitle = stage.querySelector('.stage-copy h1');
          const heroCopy = stage.querySelector('.hero-subcopy');
          const systemLine = stage.querySelector('.stage-system-line');

          if (heroTitle) {
            gsap.to(heroTitle, {
              transform: 'translate3d(0, -8%, 150px) scale(1.055)',
              opacity: 0.18,
              ease: 'none',
              scrollTrigger: { trigger: stage, start: 'top top+=66', end: 'bottom top', scrub: 0.65 },
            });
          }
          if (heroCopy) {
            gsap.to(heroCopy, {
              transform: 'translate3d(0, -18%, 210px)',
              opacity: 0,
              ease: 'none',
              scrollTrigger: { trigger: stage, start: 'top top+=66', end: 'bottom 22%', scrub: 0.65 },
            });
          }
          if (systemLine) {
            gsap.to(systemLine, {
              transform: 'translate3d(0, 28%, 90px)',
              opacity: 0.08,
              ease: 'none',
              scrollTrigger: { trigger: stage, start: 'top top+=66', end: 'bottom top', scrub: 0.65 },
            });
          }

          gsap.fromTo(
            overview.querySelectorAll('.metric-item'),
            { transform: 'translate3d(0, 34px, 0)', opacity: 0 },
            {
              transform: 'translate3d(0, 0, 0)',
              opacity: 1,
              duration: 0.85,
              stagger: 0.055,
              ease: 'power3.out',
              immediateRender: false,
              scrollTrigger: { trigger: '.metric-row', start: 'top 84%', once: true },
            },
          );

          gsap.fromTo(
            overview.querySelector('.evidence-preview'),
            { transform: 'translate3d(0, 54px, 0) scale(0.975)', opacity: 0 },
            {
              transform: 'translate3d(0, 0, 0) scale(1)',
              opacity: 1,
              duration: 1,
              ease: 'power3.out',
              immediateRender: false,
              scrollTrigger: { trigger: '.decision-preview', start: 'top 78%', once: true },
            },
          );

          ScrollTrigger.create({
            trigger: stage,
            start: 'top top+=66',
            end: 'bottom top',
            onUpdate: (self) => {
              shaderProgress = self.progress;
            },
          });
        }, overview);
        teardown.push(() => motionContext.revert());

        let frame = 0;
        let stageVisible = true;
        let renderFrame: ((time: number) => void) | undefined;
        const tick = (time: number) => {
          lenis.raf(time);
          renderFrame?.(time);
          frame = window.requestAnimationFrame(tick);
        };
        frame = window.requestAnimationFrame(tick);
        teardown.push(() => window.cancelAnimationFrame(frame));

        const visibilityObserver = new IntersectionObserver(
          ([entry]) => {
            stageVisible = entry?.isIntersecting ?? false;
          },
          { rootMargin: '180px 0px' },
        );
        visibilityObserver.observe(stage);
        teardown.push(() => visibilityObserver.disconnect());

        try {
          const THREE = await import('three');
          if (cancelled) return;

          const renderer = new THREE.WebGLRenderer({
            canvas,
            alpha: true,
            antialias: false,
            powerPreference: 'low-power',
          });
          renderer.setClearColor(0x000000, 0);
          renderer.outputColorSpace = THREE.SRGBColorSpace;

          const scene = new THREE.Scene();
          const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 30);
          camera.position.z = 6;

          const particleCount = window.innerWidth < 1100 ? 120 : 180;
          const positions = new Float32Array(particleCount * 3);
          const seeds = new Float32Array(particleCount);
          let randomState = 0x5f3759df;
          const random = () => {
            randomState = (Math.imul(randomState, 1664525) + 1013904223) >>> 0;
            return randomState / 4294967296;
          };

          for (let index = 0; index < particleCount; index += 1) {
            const offset = index * 3;
            positions[offset] = -0.4 + random() * 5.7;
            positions[offset + 1] = -3.1 + random() * 6.2;
            positions[offset + 2] = -1.5 + random() * 3;
            seeds[index] = random();
          }

          const geometry = new THREE.BufferGeometry();
          geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
          geometry.setAttribute('aSeed', new THREE.BufferAttribute(seeds, 1));

          const material = new THREE.ShaderMaterial({
            transparent: true,
            depthWrite: false,
            blending: THREE.AdditiveBlending,
            uniforms: {
              uTime: { value: 0 },
              uPointer: { value: new THREE.Vector2(0, 0) },
              uProgress: { value: 0 },
            },
            vertexShader: `
              uniform float uTime;
              uniform vec2 uPointer;
              uniform float uProgress;
              attribute float aSeed;
              varying float vAlpha;

              void main() {
                vec3 particle = position;
                float wave = sin(uTime * 0.34 + aSeed * 11.0);
                particle.x += wave * 0.10 + uPointer.x * (0.08 + aSeed * 0.16);
                particle.y += cos(uTime * 0.27 + aSeed * 8.0) * 0.09 + uPointer.y * 0.12;
                particle.z += uProgress * (aSeed - 0.5) * 2.4;

                vec4 viewPosition = modelViewMatrix * vec4(particle, 1.0);
                gl_Position = projectionMatrix * viewPosition;
                gl_PointSize = (2.2 + aSeed * 2.8) * (7.0 / -viewPosition.z);
                vAlpha = 0.20 + aSeed * 0.42;
              }
            `,
            fragmentShader: `
              uniform float uProgress;
              varying float vAlpha;

              void main() {
                float distanceToCenter = length(gl_PointCoord - vec2(0.5));
                float glow = smoothstep(0.5, 0.06, distanceToCenter);
                vec3 teal = vec3(0.24, 0.78, 0.69);
                vec3 amber = vec3(0.83, 0.49, 0.24);
                vec3 tint = mix(teal, amber, uProgress * 0.48);
                gl_FragColor = vec4(tint, glow * vAlpha);
              }
            `,
          });

          const particles = new THREE.Points(geometry, material);
          scene.add(particles);

          const pointerTarget = new THREE.Vector2(0, 0);
          const pointerCurrent = new THREE.Vector2(0, 0);
          let progressCurrent = 0;
          const onPointerMove = (event: PointerEvent) => {
            const bounds = stage.getBoundingClientRect();
            pointerTarget.set(
              ((event.clientX - bounds.left) / bounds.width - 0.5) * 2,
              -((event.clientY - bounds.top) / bounds.height - 0.5) * 2,
            );
          };
          const onPointerLeave = () => pointerTarget.set(0, 0);
          stage.addEventListener('pointermove', onPointerMove, { passive: true });
          stage.addEventListener('pointerleave', onPointerLeave);

          const resize = () => {
            const bounds = stage.getBoundingClientRect();
            const width = Math.max(1, bounds.width);
            const height = Math.max(1, bounds.height);
            renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
            renderer.setSize(width, height, false);
            camera.aspect = width / height;
            camera.updateProjectionMatrix();
          };
          const resizeObserver = new ResizeObserver(resize);
          resizeObserver.observe(stage);
          resize();

          renderFrame = (time: number) => {
            if (!stageVisible || document.visibilityState === 'hidden') return;
            pointerCurrent.lerp(pointerTarget, 0.055);
            progressCurrent += (shaderProgress - progressCurrent) * 0.06;
            material.uniforms.uTime.value = time * 0.001;
            material.uniforms.uPointer.value.copy(pointerCurrent);
            material.uniforms.uProgress.value = progressCurrent;
            particles.rotation.y = progressCurrent * -0.16;
            particles.rotation.z = progressCurrent * 0.035;
            renderer.render(scene, camera);
          };

          stage.dataset.cinematic = 'ready';
          teardown.push(() => {
            delete stage.dataset.cinematic;
            renderFrame = undefined;
            stage.removeEventListener('pointermove', onPointerMove);
            stage.removeEventListener('pointerleave', onPointerLeave);
            resizeObserver.disconnect();
            geometry.dispose();
            material.dispose();
            renderer.dispose();
            renderer.forceContextLoss();
          });
        } catch {
          canvas.dataset.state = 'fallback';
        }

        ScrollTrigger.refresh();
      } catch {
        canvas.dataset.state = 'fallback';
      }
    };

    const scheduleBoot = () => {
      if (started || cancelled) return;
      if (idleWindow.requestIdleCallback) {
        idleHandle = idleWindow.requestIdleCallback(() => void boot(), { timeout: 1200 });
      } else {
        timeoutHandle = window.setTimeout(() => void boot(), 180);
      }
    };

    const entryObserver = new IntersectionObserver(
      ([entry]) => {
        if (!entry?.isIntersecting) return;
        entryObserver.disconnect();
        scheduleBoot();
      },
      { rootMargin: '240px 0px' },
    );
    entryObserver.observe(stage);

    return () => {
      cancelled = true;
      entryObserver.disconnect();
      if (idleHandle !== undefined) idleWindow.cancelIdleCallback?.(idleHandle);
      if (timeoutHandle !== undefined) window.clearTimeout(timeoutHandle);
      for (const dispose of teardown.reverse()) dispose();
    };
  }, []);

  return <canvas ref={canvasRef} className="cinematic-canvas" aria-hidden="true" />;
}
