import { Fragment } from "react";
import { PipelineNodeCard } from "./PipelineNodeCard";
import { PipelineEdgeArrow } from "./PipelineEdgeArrow";
import type { PipelineEdgeDef, PipelineNodeDef, PipelineNodeId } from "./data";

interface Props {
  nodes: PipelineNodeDef[];
  edges: PipelineEdgeDef[];
  selectedNode: PipelineNodeId | null;
  onSelectNode: (id: PipelineNodeId | null) => void;
  animated: boolean;
}

export function PipelineFlow({ nodes, edges, selectedNode, onSelectNode, animated }: Props) {
  return (
    <div className="pipeline-flow">
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 0 }}>
        {nodes.map((node, i) => (
          <Fragment key={node.id}>
            <PipelineNodeCard
              node={node}
              isSelected={selectedNode === node.id}
              onSelect={() => onSelectNode(selectedNode === node.id ? null : node.id)}
            />
            {i < nodes.length - 1 && <PipelineEdgeArrow edge={edges[i]} animated={animated} />}
          </Fragment>
        ))}
      </div>
      <div
        style={{
          textAlign: "center",
          marginTop: 12,
          fontSize: 10,
          color: "var(--text-4)",
          fontFamily: "var(--font-mono)",
        }}
      >
        노드를 클릭하면 상세 정보를 확인할 수 있습니다
      </div>
    </div>
  );
}
