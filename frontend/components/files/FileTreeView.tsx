"use client";

import { useState } from "react";
import type { FileTreeNode } from "@/lib/fileTree";

/* Collapsible file tree for the repo file browser (R12).

   One recursive component: a directory renders a row for itself, then maps
   its children through the same component again. Each rendered node gets
   its own independent expand/collapse state — expanding one folder never
   touches any other's. */

function IssueBadge({ count }: { count: number }) {
  if (count === 0) return null;
  return <span className="font-mono text-[10px] text-critical">{count}</span>;
}

function TreeNode({
  node,
  depth,
  selectedPath,
  onSelect,
}: {
  node: FileTreeNode;
  depth: number;
  selectedPath: string | null;
  onSelect: (path: string) => void;
}) {
  // Starts expanded — collapsing is a deliberate action from here, not the
  // tree's default state, so the browser doesn't open on a wall of folders.
  const [expanded, setExpanded] = useState(true);

  if (node.isDirectory) {
    return (
      <li>
        <button
          type="button"
          onClick={() => setExpanded((e) => !e)}
          className="flex w-full items-center gap-2 py-1 text-left font-mono text-xs text-muted transition-colors hover:text-parchment"
          style={{ paddingLeft: `${depth * 16}px` }}
        >
          <span className="w-3 text-rule">{expanded ? "▾" : "▸"}</span>
          <span className="truncate">{node.name}/</span>
          <IssueBadge count={node.findingCount} />
        </button>
        {expanded && node.children.length > 0 && (
          <ul>
            {node.children.map((child) => (
              <TreeNode
                key={child.path}
                node={child}
                depth={depth + 1}
                selectedPath={selectedPath}
                onSelect={onSelect}
              />
            ))}
          </ul>
        )}
      </li>
    );
  }

  const isSelected = node.path === selectedPath;
  return (
    <li>
      <button
        type="button"
        onClick={() => onSelect(node.path)}
        className={`flex w-full items-center gap-2 py-1 text-left font-mono text-xs transition-colors hover:text-parchment ${
          isSelected ? "text-parchment" : "text-muted"
        }`}
        style={{ paddingLeft: `${depth * 16 + 20}px` }}
      >
        <span className="truncate">{node.name}</span>
        <IssueBadge count={node.findingCount} />
      </button>
    </li>
  );
}

export function FileTreeView({
  root,
  selectedPath,
  onSelect,
}: {
  root: FileTreeNode;
  selectedPath: string | null;
  onSelect: (path: string) => void;
}) {
  return (
    <ul className="space-y-0.5">
      {root.children.map((child) => (
        <TreeNode
          key={child.path}
          node={child}
          depth={0}
          selectedPath={selectedPath}
          onSelect={onSelect}
        />
      ))}
    </ul>
  );
}
