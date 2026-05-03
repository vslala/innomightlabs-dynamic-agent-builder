import * as vscode from 'vscode';

export type ExtensionConfig = {
	baseUrl: string;
	apiKey: string;
};

export class ExtensionConfigService {
	public getConfig(): ExtensionConfig {
		const config = vscode.workspace.getConfiguration('innomightlabsCodeAssist');

		return {
			baseUrl: config.get<string>('apiBaseUrl', '').trim(),
			apiKey: config.get<string>('apiKey', '').trim(),
		};
	}

	public isConfigured(): boolean {
		const config = this.getConfig();
		return config.baseUrl.length > 0 && config.apiKey.length > 0;
	}
}
