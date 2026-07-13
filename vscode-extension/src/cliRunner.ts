import * as vscode from 'vscode';
import { execSync } from 'child_process';

export class CliRunner {
    private output: vscode.OutputChannel;

    constructor() {
        this.output = vscode.window.createOutputChannel('UDR');
    }

    get cliPath(): string {
        return vscode.workspace.getConfiguration('udr').get('cliPath', 'udr');
    }

    run(args: string[]): void {
        const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || '.';
        const cmd = `${this.cliPath} ${args.join(' ')}`;
        this.output.clear();
        this.output.appendLine(`$ ${cmd}`);
        this.output.show();

        try {
            const result = execSync(cmd, { cwd: workspaceRoot, encoding: 'utf-8', timeout: 120000 });
            this.output.appendLine(result);
        } catch (err: any) {
            this.output.appendLine(`[error] ${err.stderr || err.message}`);
            vscode.window.showErrorMessage(`UDR: ${err.message}`);
        }
    }

    runSilent(args: string[]): string {
        const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || '.';
        try {
            return execSync(`${this.cliPath} ${args.join(' ')}`, {
                cwd: workspaceRoot, encoding: 'utf-8', timeout: 60000,
            });
        } catch {
            return '';
        }
    }
}
