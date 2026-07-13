import * as vscode from 'vscode';
import { CliRunner } from './cliRunner';
import { readFileSync, writeFileSync } from 'fs';

export class ManifestEditor {
    constructor(private cli: CliRunner) {}

    async addDependency(uri?: vscode.Uri): Promise<void> {
        if (!uri) uri = vscode.window.activeTextEditor?.document.uri;
        if (!uri) return;

        const name = await vscode.window.showInputBox({ prompt: 'Dependency name', placeHolder: 'e.g. requests' });
        if (!name) return;
        const version = await vscode.window.showInputBox({ prompt: 'Version constraint', placeHolder: 'e.g. >=2.28' });
        if (!version) return;

        const doc = await vscode.workspace.openTextDocument(uri);
        const content = doc.getText();
        const fileName = uri.fsPath.split('/').pop() || '';

        if (fileName === 'requirements.txt') {
            this._appendLine(uri, `${name}${version}`);
        } else if (fileName === 'pyproject.toml') {
            this._replaceInSection(uri, content, /\[project\.dependencies\]/, (section) =>
                section + `\n${name} = "${version}"`
            );
        } else if (fileName === 'package.json') {
            this._updateJSON(uri, content, 'dependencies', name, version);
        } else {
            vscode.window.showInformationMessage(`Unsupported manifest: ${fileName}. Add dependency manually.`);
        }
    }

    async updateDependency(uri?: vscode.Uri): Promise<void> {
        if (!uri) uri = vscode.window.activeTextEditor?.document.uri;
        if (!uri) return;

        const name = await vscode.window.showInputBox({ prompt: 'Dependency name to update' });
        if (!name) return;
        const newVersion = await vscode.window.showInputBox({ prompt: 'New version constraint' });
        if (!newVersion) return;

        const doc = await vscode.workspace.openTextDocument(uri);
        const content = doc.getText();
        const fileName = uri.fsPath.split('/').pop() || '';

        if (fileName === 'requirements.txt') {
            const updated = content.replace(
                new RegExp(`^${name}[><=!].*$`, 'm'),
                `${name}${newVersion}`
            );
            if (updated !== content) {
                const edit = new vscode.WorkspaceEdit();
                edit.replace(uri, new vscode.Range(0, 0, doc.lineCount, 0), updated);
                vscode.workspace.applyEdit(edit);
            }
        } else if (fileName === 'package.json') {
            this._updateJSON(uri, content, 'dependencies', name, newVersion);
        } else {
            vscode.window.showInformationMessage(`Manual edit needed for ${fileName}`);
        }
    }

    async removeDependency(uri?: vscode.Uri): Promise<void> {
        if (!uri) uri = vscode.window.activeTextEditor?.document.uri;
        if (!uri) return;

        const name = await vscode.window.showInputBox({ prompt: 'Dependency name to remove' });
        if (!name) return;

        const doc = await vscode.workspace.openTextDocument(uri);
        const content = doc.getText();
        const fileName = uri.fsPath.split('/').pop() || '';

        if (fileName === 'requirements.txt') {
            const updated = content.replace(new RegExp(`^${name}[>=<!].*\n?`, 'm'), '');
            const edit = new vscode.WorkspaceEdit();
            edit.replace(uri, new vscode.Range(0, 0, doc.lineCount, 0), updated);
            vscode.workspace.applyEdit(edit);
        } else if (fileName === 'package.json') {
            try {
                const json = JSON.parse(content);
                delete (json.dependencies || {})[name];
                writeFileSync(uri.fsPath, JSON.stringify(json, null, 2) + '\n');
            } catch { /* ignore */ }
        }
    }

    private _appendLine(uri: vscode.Uri, line: string): void {
        const edit = new vscode.WorkspaceEdit();
        const doc = vscode.workspace.textDocuments.find(d => d.uri.fsPath === uri.fsPath);
        if (doc) {
            const lastLine = doc.lineAt(doc.lineCount - 1);
            edit.insert(uri, lastLine.range.end, `\n${line}`);
            vscode.workspace.applyEdit(edit);
        }
    }

    private _replaceInSection(uri: vscode.Uri, content: string, pattern: RegExp, transform: (s: string) => string): void {
        const match = content.match(pattern);
        if (match && match.index !== undefined) {
            const start = content.indexOf('\n', match.index) + 1;
            const end = content.indexOf('\n[', start);
            const sectionEnd = end > 0 ? end : content.length;
            const section = content.substring(start, sectionEnd);
            const updated = content.substring(0, start) + transform(section) + content.substring(sectionEnd);
            const doc = vscode.workspace.textDocuments.find(d => d.uri.fsPath === uri.fsPath);
            if (doc) {
                const edit = new vscode.WorkspaceEdit();
                edit.replace(uri, new vscode.Range(0, 0, doc.lineCount, 0), updated);
                vscode.workspace.applyEdit(edit);
            }
        }
    }

    private _updateJSON(uri: vscode.Uri, content: string, section: string, name: string, value: string): void {
        try {
            const json = JSON.parse(content);
            if (!json[section]) json[section] = {};
            json[section][name] = value;
            writeFileSync(uri.fsPath, JSON.stringify(json, null, 2) + '\n');
        } catch { /* ignore */ }
    }
}
