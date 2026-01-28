import * as fs from "node:fs/promises";
import * as path from "node:path";
import * as ts from "typescript";
import type { SymbolInfo } from "src/shared/types/rpc";

const isSourceFile = (file: string): boolean => {
  const ext = path.extname(file).toLowerCase();
  return [".ts", ".tsx", ".js", ".jsx"].includes(ext);
};

const hasExportModifier = (node: ts.Node): boolean => {
  if (!ts.canHaveModifiers(node)) {
    return false;
  }

  const modifiers = ts.getModifiers(node) ?? [];
  return modifiers.some((modifier) => modifier.kind === ts.SyntaxKind.ExportKeyword);
};

const collectSymbols = (sourceFile: ts.SourceFile): string[] => {
  const symbols = new Set<string>();

  const visit = (node: ts.Node): void => {
    if (ts.isExportAssignment(node)) {
      symbols.add("default");
    }

    if (ts.isExportDeclaration(node) && node.exportClause && ts.isNamedExports(node.exportClause)) {
      for (const element of node.exportClause.elements) {
        symbols.add(element.name.text);
      }
    }

    if (hasExportModifier(node)) {
      if (ts.isFunctionDeclaration(node) && node.name) {
        symbols.add(node.name.text);
      }

      if (ts.isClassDeclaration(node) && node.name) {
        symbols.add(node.name.text);
      }

      if (ts.isInterfaceDeclaration(node)) {
        symbols.add(node.name.text);
      }

      if (ts.isTypeAliasDeclaration(node)) {
        symbols.add(node.name.text);
      }

      if (ts.isVariableStatement(node)) {
        for (const declaration of node.declarationList.declarations) {
          if (ts.isIdentifier(declaration.name)) {
            symbols.add(declaration.name.text);
          }
        }
      }
    }

    ts.forEachChild(node, visit);
  };

  visit(sourceFile);
  return Array.from(symbols);
};

export const extractExportedSymbols = async (files: string[]): Promise<SymbolInfo[]> => {
  const results: SymbolInfo[] = [];

  for (const file of files) {
    if (!isSourceFile(file)) {
      continue;
    }

    try {
      const content = await fs.readFile(file, "utf8");
      const sourceFile = ts.createSourceFile(file, content, ts.ScriptTarget.Latest, true);
      results.push({
        path: file,
        exports: collectSymbols(sourceFile),
      });
    } catch {
      results.push({ path: file, exports: [] });
    }
  }

  return results;
};
