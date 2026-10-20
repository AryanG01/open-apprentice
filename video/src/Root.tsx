import { Composition } from "remotion";
import { Demo } from "./Demo";
import { FPS, timeline } from "./timeline";

export const Root = () => {
  const t = timeline();
  return <Composition id="Demo" component={Demo} durationInFrames={Math.ceil(t.total * FPS)} fps={FPS} width={1920} height={1080} />;
};
