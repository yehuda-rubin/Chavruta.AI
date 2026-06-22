/**
 * The UI design lives entirely in the static HTML mockup
 * (public/ui/chavruta.html — the approved "Modern Glass" design, mockup #5).
 * React just "launches" that file in a full-screen frame so the rendered
 * design is byte-identical to the mockup (its own Tailwind CDN + fonts),
 * with no interference from the app's build-time Tailwind.
 *
 * Data wiring (sessions / chat / sources) is decoupled for now and can be
 * re-connected to the backend from inside the HTML or via postMessage.
 */
export default function App() {
  return (
    <iframe
      src="/ui/chavruta.html"
      title="Chavruta.AI"
      className="w-screen h-screen border-0 block"
    />
  )
}
