import * as vscode from 'vscode';
import { CliRunner } from './cliRunner';

export class CVEDiagnostics {
    private collection: vscode.DiagnosticCollection;

    constructor(context: vscode.ExtensionContext) {
        this.collection = vscode.languages.createDiagnosticCollection('udr-cve');
        context.subscriptions.push(this.collection);
    }

    startWatching(): void {
        const watcher = vscode.workspace.createFileSystemWatcher('**/udr.lock');
        watcher.onDidChange((uri) => {
            vscode.workspace.openTextDocument(uri).then((doc) => this.update(doc), () => {});
        });
    }

    checkOnOpen(): void {
        vscode.workspace.findFiles('**/udr.lock', null, 1).then((files) => {
            if (files.length > 0) {
                vscode.workspace.openTextDocument(files[0]).then((doc) => this.update(doc), () => {});
            }
        });
    }

    update(document: vscode.TextDocument): void {
        if (!document.fileName.endsWith('udr.lock')) return;

        const diagnostics: vscode.Diagnostic[] = [];
        try {
            const lock = JSON.parse(document.getText());
            const pkgs = lock.packages || {};

            for (const [name, info] of Object.entries(pkgs)) {
                const pkg = info as any;
                const vulns: any[] = pkg.vulnerabilities || [];
                if (vulns.length === 0) continue;

                const text = document.getText();
                const idx = text.indexOf(`"${name}"`);
                if (idx === -1) continue;
                const pos = document.positionAt(idx);
                const endPos = document.positionAt(idx + name.length + 2);
                const range = new vscode.Range(pos, endPos);

                for (const vuln of vulns) {
                    const diag = new vscode.Diagnostic(
                        range,
                        `[CVE] ${vuln.id || 'unknown'}: ${(vuln.summary || '').substring(0, 100)}`,
                        vscode.DiagnosticSeverity.Warning
                    );
                    diag.source = 'UDR';
                    diag.code = vuln.id;
                    diag.relatedInformation = [
                        new vscode.DiagnosticRelatedInformation(
                            new vscode.Location(document.uri, range),
                            `Fixed in: ${vuln.fixed_version || 'unknown'}`
                        ),
                    ];
                    diagnostics.push(diag);
                }
            }
        } catch {
            // invalid JSON - skip
        }

        this.collection.set(document.uri, diagnostics);

        const cveCount = diagnostics.length;
        if (cveCount > 0) {
            vscode.window.showWarningMessage(`UDR: ${cveCount} known vulnerabilities found in lock file`);
        }
    }
}
