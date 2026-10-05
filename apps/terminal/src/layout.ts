import Yoga from "yoga-layout";

export interface TerminalLayout {
  contentWidth: number;
  transcriptHeight: number;
  inputWidth: number;
}

export function computeTerminalLayout(
  columns: number,
  rows: number,
): TerminalLayout {
  const width = Math.max(columns, 40);
  const height = Math.max(rows, 12);

  const root = Yoga.Node.create();
  const header = Yoga.Node.create();
  const transcript = Yoga.Node.create();
  const input = Yoga.Node.create();

  root.setWidth(width);
  root.setHeight(height);
  root.setFlexDirection(Yoga.FLEX_DIRECTION_COLUMN);
  root.setPadding(Yoga.EDGE_LEFT, 1);
  root.setPadding(Yoga.EDGE_RIGHT, 1);

  header.setHeight(3);
  transcript.setFlexGrow(1);
  input.setHeight(3);

  root.insertChild(header, 0);
  root.insertChild(transcript, 1);
  root.insertChild(input, 2);
  root.calculateLayout(width, height, Yoga.DIRECTION_LTR);

  const result = {
    contentWidth: Math.max(20, Math.floor(root.getComputedWidth() - 2)),
    transcriptHeight: Math.max(4, Math.floor(transcript.getComputedHeight())),
    inputWidth: Math.max(20, Math.floor(input.getComputedWidth())),
  };

  root.freeRecursive();
  return result;
}
