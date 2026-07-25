import * as vscode from 'vscode';
import { spawnSync } from 'child_process';

export class CliRunner {
    private output: vscode.OutputChannel;

    constructor() {
        this.output = vscode.window.createOutputChannel('UDR');
    }

    get cliPath(): string {
        return vscode.workspace.getConfiguration('udr').get('cliPath', 'udr');
    }

    isAvailable(): boolean {
        try {
            const result = spawnSync(this.cliPath, ['--version'], { timeout: 5000, encoding: 'utf-8' });
            return result.status === 0;
        } catch {
            return false;
        }
    }

    run(args: string[]): void {
        const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || '.';
        this.output.clear();
        this.output.appendLine(`$ ${this.cliPath} ${args.join(' ')}`);
        this.output.show();

        try {
            const result = spawnSync(this.cliPath, args, {
                cwd: workspaceRoot, encoding: 'utf-8', timeout: 120000,
            });
            if (result.status === 0) {
                this.output.appendLine(result.stdout || '');
            } else {
                const errMsg = result.stderr || `exit code ${result.status}`;
                this.output.appendLine(`[error] ${errMsg}`);
                vscode.window.showErrorMessage(`UDR: ${errMsg}`);
            }
        } catch (err: any) {
            this.output.appendLine(`[error] ${err.stderr || err.message}`);
            vscode.window.showErrorMessage(`UDR: ${err.message}`);
        }
    }

    runSilent(args: string[]): string {
        const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || '.';
        try {
            const result = spawnSync(this.cliPath, args, {
                cwd: workspaceRoot, encoding: 'utf-8', timeout: 60000,
            });
            return result.status === 0 ? (result.stdout || '') : '';
        } catch {
            return '';
        }
    }
}
