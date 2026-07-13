import * as assert from 'assert';
import * as vscode from 'vscode';

suite('UDR Extension Tests', () => {
    test('Extension should be present', () => {
        assert.ok(vscode.extensions.getExtension('udr-vscode'));
    });

    test('Commands should be registered', async () => {
        const commands = await vscode.commands.getCommands(true);
        const udrCommands = commands.filter((c) => c.startsWith('udr.'));
        assert.ok(udrCommands.length >= 10, `Expected >=10 UDR commands, got ${udrCommands.length}`);
        assert.ok(udrCommands.includes('udr.check'));
        assert.ok(udrCommands.includes('udr.lock'));
        assert.ok(udrCommands.includes('udr.generateSbom'));
    });

    test('Views should be contributed', () => {
        const views = vscode.window.createTreeView('udrLockView', { treeDataProvider: { getChildren: () => [], getTreeItem: (e: any) => e } });
        assert.ok(views);
        views.dispose();
    });
});
