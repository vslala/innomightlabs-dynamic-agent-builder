import * as vscode from 'vscode';

const API_BASE_URL_STORAGE_KEY = 'innomightlabs.apiBaseUrl';
const API_KEY_SECRET_KEY = 'innomightlabs.apiKey';

export type ExtensionConfig = {
	baseUrl: string;
	apiKey: string;
};

export class ExtensionConfigService {
	public constructor(private readonly context: vscode.ExtensionContext) {}

	public async getConfig(): Promise<ExtensionConfig> {
		const config = vscode.workspace.getConfiguration('innomightlabsCodeAssist');
		const storedBaseUrl = this.context.globalState.get<string>(API_BASE_URL_STORAGE_KEY, '').trim();
		const storedApiKey = (await this.context.secrets.get(API_KEY_SECRET_KEY) ?? '').trim();

		return {
			baseUrl: storedBaseUrl || config.get<string>('apiBaseUrl', '').trim(),
			apiKey: storedApiKey || config.get<string>('apiKey', '').trim(),
		};
	}

	public async isConfigured(): Promise<boolean> {
		const config = await this.getConfig();
		return config.baseUrl.length > 0 && config.apiKey.length > 0;
	}

	/**
	 * Prompts the user to configure the backend base URL and API key, validates both inputs,
	 * stores the base URL in global state and the API key in secret storage, and returns the
	 * saved configuration. Returns `null` if the user cancels either input step.
	 */	
	public async configure(): Promise<ExtensionConfig | null> {
		const currentConfig = await this.getConfig();
		const baseUrl = await vscode.window.showInputBox({
			title: 'Configure Innomightlabs Backend',
			prompt: 'Backend API base URL',
			placeHolder: 'https://api.example.com',
			value: currentConfig.baseUrl,
			ignoreFocusOut: true,
			validateInput: (value) => {
				const trimmed = value.trim();
				if (!trimmed) {
					return 'Base URL is required.';
				}
				try {
					const parsed = new URL(trimmed);
					if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
						return 'Base URL must start with http:// or https://.';
					}
				} catch {
					return 'Enter a valid URL.';
				}
				return null;
			},
		});

		if (baseUrl === undefined) {
			return null;
		}

		const apiKey = await vscode.window.showInputBox({
			title: 'Configure Innomightlabs Backend',
			prompt: 'Backend API key',
			password: true,
			value: currentConfig.apiKey,
			ignoreFocusOut: true,
			validateInput: (value) => value.trim() ? null : 'API key is required.',
		});

		if (apiKey === undefined) {
			return null;
		}

		const savedConfig = {
			baseUrl: baseUrl.trim().replace(/\/+$/, ''),
			apiKey: apiKey.trim(),
		};

		await this.context.globalState.update(API_BASE_URL_STORAGE_KEY, savedConfig.baseUrl);
		await this.context.secrets.store(API_KEY_SECRET_KEY, savedConfig.apiKey);
		return savedConfig;
	}
}
