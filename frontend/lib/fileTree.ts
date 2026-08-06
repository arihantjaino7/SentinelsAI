/* Turns the flat file list `GET /scans/{id}/files` returns into a nested
   tree the file-tree browser (R12) can render as collapsible folders. */

import type { RepoFileEntry } from "@/lib/api";

export interface FileTreeNode {
  name: string;               // this segment only, e.g. "main.py"
  path: string;                // full forward-slash path from the repo root
  isDirectory: boolean;
  size: number;                 // bytes; for a directory, sum of its files
  findingCount: number;        // for a directory, sum of its files'
  language: string | null;     // null for directories
  children: FileTreeNode[];
}

/** Build the nested tree. The returned node is a synthetic root — render
 * its `children`, not the node itself. */
export function buildFileTree(files: RepoFileEntry[]): FileTreeNode {
  const root: FileTreeNode = {
    name: "",
    path: "",
    isDirectory: true,
    size: 0,
    findingCount: 0,
    language: null,
    children: [],
  };

  for (const file of files) {
    const parts = file.path.split("/");
    let node = root;
    let builtPath = "";

    parts.forEach((part, i) => {
      builtPath = builtPath ? `${builtPath}/${part}` : part;
      const isLeaf = i === parts.length - 1;

      let child = node.children.find((c) => c.name === part);
      if (!child) {
        child = {
          name: part,
          path: builtPath,
          isDirectory: !isLeaf,
          size: 0,
          findingCount: 0,
          language: null,
          children: [],
        };
        node.children.push(child);
      }
      node = child;
    });

    node.size = file.size;
    node.findingCount = file.finding_count;
    node.language = file.language;
  }

  sortAndRollUp(root);
  return root;
}

// Directories first, alphabetical within each group — then, for directories,
// sum their children's size/findingCount bottom-up so a folder's badge shows
// its whole subtree's issue count without a second pass over the flat list.
function sortAndRollUp(node: FileTreeNode): void {
  node.children.forEach(sortAndRollUp);
  node.children.sort((a, b) => {
    if (a.isDirectory !== b.isDirectory) return a.isDirectory ? -1 : 1;
    return a.name.localeCompare(b.name);
  });
  if (node.isDirectory) {
    node.size = node.children.reduce((sum, c) => sum + c.size, 0);
    node.findingCount = node.children.reduce((sum, c) => sum + c.findingCount, 0);
  }
}
