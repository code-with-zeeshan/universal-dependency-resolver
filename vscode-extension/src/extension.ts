import * as vscode from 'vscode';
import { LockFileProvider } from './lockFileProvider';
import { CVEDiagnostics } from './cveDiagnostics';
import { CliRunner } from './cliRunner';
import { ManifestEditor } from './manifestEditor';

export function activate(context: vscode.ExtensionContext) {
    const cli = new CliRunner();

    if (!cli.isAvailable()) {
        const action = 'Install UDR';
        vscode.window.showErrorMessage(
            'UDR CLI not found — install it with `pip install ud-resolver` or set `udr.cliPath`',
            action
        ).then(selected => {
            if (selected === action) {
                vscode.env.openExternal(vscode.Uri.parse('https://opencode.ai'));
            }
        });
        return;
    }

    const diagnostics = new CVEDiagnostics(context);
    const lockProvider = new LockFileProvider(cli);
    const manifestEditor = new ManifestEditor(cli);

    vscode.window.registerTreeDataProvider('udrLockView', lockProvider);

    context.subscriptions.push(
        vscode.commands.registerCommand('udr.check', () => cli.run(['check', '--cve', '--deprecated'])),
        vscode.commands.registerCommand('udr.updatePackage', async () => {
            const pkg = await vscode.window.showInputBox({ prompt: 'Package name', placeHolder: 'e.g. requests' });
            if (pkg) cli.run(['update', pkg]);
        }),
        vscode.commands.registerCommand('udr.generateSbom', () => cli.run(['sbom'])),
        vscode.commands.registerCommand('udr.verify', () => cli.run(['verify'])),
        vscode.commands.registerCommand('udr.checkPolicies', () => cli.run(['check', '--policy'])),
        vscode.commands.registerCommand('udr.fixCves', () => cli.run(['update', '--fix-cve'])),
        vscode.commands.registerCommand('udr.lock', () => cli.run(['lock'])),
        vscode.commands.registerCommand('udr.lockCheck', () => cli.run(['lock', '--check'])),
        vscode.commands.registerCommand('udr.showGraph', () => cli.run(['graph'])),
        vscode.commands.registerCommand('udr.showPackageDetails', (name, ecosystem) => {
            cli.run(['resolve', name || '']);
        }),
        vscode.commands.registerCommand('udr.addDependency', (uri) => manifestEditor.addDependency(uri)),
        vscode.commands.registerCommand('udr.updateDependency', (uri) => manifestEditor.updateDependency(uri)),
        vscode.commands.registerCommand('udr.removeDependency', (uri) => manifestEditor.removeDependency(uri)),
        vscode.commands.registerCommand('udr.refreshLockView', () => lockProvider.refresh()),
        vscode.workspace.onDidSaveTextDocument((doc) => {
            if (doc.fileName.endsWith('udr.lock')) {
                diagnostics.update(doc);
                lockProvider.refresh();
            }
        })
    );

    diagnostics.startWatching();
    diagnostics.checkOnOpen();
}

export function deactivate() {}
