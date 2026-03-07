/**
 * Extension Tests
 * Basic test suite for DataShark extension
 */

import * as assert from 'assert';
import * as vscode from 'vscode';

suite('DataShark Extension Test Suite', () => {
    vscode.window.showInformationMessage('Starting DataShark tests');

    test('Extension should be present', () => {
        assert.ok(vscode.extensions.getExtension('datashark.datashark'));
    });

    test('Should register all commands', async () => {
        const commands = await vscode.commands.getCommands(true);
        const datasharkCommands = commands.filter(cmd => cmd.startsWith('datashark.'));
        
        assert.ok(datasharkCommands.length >= 8, 'Should have at least 8 commands registered');
        assert.ok(commands.includes('datashark.toggleDatabaseMode'));
        assert.ok(commands.includes('datashark.refreshMetadata'));
        assert.ok(commands.includes('datashark.previewTableData'));
        assert.ok(commands.includes('datashark.generateSelectQuery'));
    });

    test('Tree view should be registered', () => {
        const treeView = vscode.window.createTreeView('datashark.schemaTree', {
            treeDataProvider: {
                getTreeItem: (element: any) => element,
                getChildren: () => []
            }
        });
        assert.ok(treeView);
        treeView.dispose();
    });
});
















