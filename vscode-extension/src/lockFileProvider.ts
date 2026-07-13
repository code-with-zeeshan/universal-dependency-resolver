import * as vscode from 'vscode';
import { CliRunner } from './cliRunner';
import { readFileSync } from 'fs';
import { join } from 'path';

export class LockFileProvider implements vscode.TreeDataProvider<LockEntry> {
    private _onDidChangeTreeData = new vscode.EventEmitter<LockEntry | undefined>();
    readonly onDidChangeTreeData = this._onDidChangeTreeData.event;
    private lockData: any = null;

    constructor(private cli: CliRunner) {
        this.loadLockFile();
    }

    refresh(): void {
        this.loadLockFile();
        this._onDidChangeTreeData.fire(undefined);
    }

    getTreeItem(element: LockEntry): vscode.TreeItem {
        return element;
    }

    getChildren(element?: LockEntry): Thenable<LockEntry[]> {
        if (!this.lockData) return Promise.resolve([new LockEntry('No udr.lock found', '', vscode.TreeItemCollapsibleState.None)]);

        if (!element) {
            const groups = new Map<string, LockEntry[]>();
            for (const [name, info] of Object.entries(this.lockData.packages || {})) {
                const eco = (info as any).ecosystem || 'unknown';
                if (!groups.has(eco)) groups.set(eco, []);
                groups.get(eco)!.push(new LockEntry(
                    name,
                    `${(info as any).resolved_version || '?'} | ${(info as any).license || 'no-license'}`,
                    vscode.TreeItemCollapsibleState.None,
                    {
                        command: 'udr.showPackageDetails',
                        title: '',
                        arguments: [name, (info as any).ecosystem],
                    }
                ));
            }
            return Promise.resolve(
                Array.from(groups.entries()).map(([eco, children]) =>
                    new LockEntry(
                        `${eco} (${children.length})`,
                        '',
                        vscode.TreeItemCollapsibleState.Collapsed,
                        undefined,
                        children
                    )
                )
            );
        }
        return Promise.resolve(element.children || []);
    }

    private loadLockFile(): void {
        const root = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
        if (!root) return;
        try {
            const content = readFileSync(join(root, 'udr.lock'), 'utf-8');
            this.lockData = JSON.parse(content);
        } catch {
            this.lockData = null;
        }
    }
}

export class LockEntry extends vscode.TreeItem {
    constructor(
        public readonly label: string,
        public readonly description: string,
        public readonly collapsibleState: vscode.TreeItemCollapsibleState,
        public readonly command?: vscode.Command,
        public readonly children?: LockEntry[]
    ) {
        super(label, collapsibleState);
        this.tooltip = description;
        if (label.includes('CVE') || description.includes('CVE')) {
            this.iconPath = new vscode.ThemeIcon('warning', new vscode.ThemeColor('errorForeground'));
        } else {
            this.iconPath = new vscode.ThemeIcon('package');
        }
    }
}
