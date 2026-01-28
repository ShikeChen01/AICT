import * as fs from "node:fs/promises";
import * as path from "node:path";
import * as ts from "typescript";

export type ImportGraph = Record<string, string[]>;

const isSourceFile = (file: string): boolean => {
  const ext = path.extname(file).toLowerCase();
  return [".ts", ".tsx", ".js", ".jsx"].includes(ext);
};

const collectImports = (sourceFile: ts.SourceFile): string[] => {
  const imports: string[] = [];

  const visit = (node: ts.Node): void => {
    if (ts.isImportDeclaration(node) && node.moduleSpecifier && ts.isStringLiteral(node.moduleSpecifier)) {
      imports.push(node.moduleSpecifier.text);
    }

    if (ts.isExportDeclaration(node) && node.moduleSpecifier && ts.isStringLiteral(node.moduleSpecifier)) {
      imports.push(node.moduleSpecifier.text);
    }

    if (
      ts.isCallExpression(node) &&
      ts.isIdentifier(node.expression) &&
      node.expression.text === "require" &&
      node.arguments.length === 1 &&
      ts.isStringLiteral(node.arguments[0])
    ) {
      imports.push(node.arguments[0].text);
    }

    ts.forEachChild(node, visit);
  };

  visit(sourceFile);
  return imports;
};

export const buildImportGraph = async (files: string[]): Promise<ImportGraph> => {
  const graph: ImportGraph = {};

  for (const file of files) {
    if (!isSourceFile(file)) {
      continue;
    }

    try {
      const content = await fs.readFile(file, "utf8");
      const sourceFile = ts.createSourceFile(file, content, ts.ScriptTarget.Latest, true);
      graph[file] = collectImports(sourceFile);
    } catch {
      graph[file] = [];
    }
  }

  return graph;
};
