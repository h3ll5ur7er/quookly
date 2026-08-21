/** What this needs from a browser that has it, and nothing more. */
type AudioContextConstructor = new () => AudioContext;

let context: AudioContext | null = null;

/**
 * Wake the context on a gesture the cook has already made.
 *
 * Browsers refuse to start audio without one, and the first sound a timer makes would be
 * silence if the context were created when the timer finished rather than when the cook
 * tapped start. Cheap to call more than once.
 */
export function readyToSound(): void {
  if (context !== null) {
    return;
  }
  const Constructor = (window as Window & { AudioContext?: AudioContextConstructor }).AudioContext;
  if (Constructor === undefined) {
    return;
  }
  try {
    context = new Constructor();
  } catch {
    // No audio. The timer still goes off; it just does so quietly.
    context = null;
  }
}

/**
 * Say that a timer has finished, in whatever ways this device can.
 *
 * A kitchen is noisy and a phone on a worktop cannot be felt, so both: a short tone and a
 * buzz. Neither is load-bearing — the screen says so too, and a browser that offers
 * neither still shows a timer that has run out.
 */
export function sound(): void {
  navigator.vibrate?.([200, 100, 200]);

  if (context === null) {
    return;
  }
  const now = context.currentTime;
  const tone = context.createOscillator();
  const level = context.createGain();
  // A plain sine at a pitch that carries across a room without being shrill. Generated
  // rather than loaded: an audio file is a request that fails exactly when the kitchen
  // has no signal, which is when this is most needed (NFR-13).
  tone.frequency.value = 880;
  level.gain.setValueAtTime(0.0001, now);
  level.gain.exponentialRampToValueAtTime(0.3, now + 0.02);
  level.gain.exponentialRampToValueAtTime(0.0001, now + 0.6);
  tone.connect(level).connect(context.destination);
  tone.start(now);
  tone.stop(now + 0.6);
}
