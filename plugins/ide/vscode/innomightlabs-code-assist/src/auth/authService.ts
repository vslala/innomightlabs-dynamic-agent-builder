import * as vscode from 'vscode';

import type { ExtensionConfigService } from '../config/extensionConfigService';

const VISITOR_TOKEN_SECRET_KEY = 'innomightlabs.visitorToken';
const VISITOR_INFO_STORAGE_KEY = 'innomightlabs.visitorInfo';

export type VisitorInfo = {
	visitorId: string;
	email: string;
	name: string;
	picture: string | null;
};

export type AuthSession = {
	token: string;
	visitor: VisitorInfo;
};

export type AuthState = {
	isAuthenticated: boolean;
	isAuthenticating: boolean;
	visitor: VisitorInfo | null;
};

export class AuthService implements vscode.UriHandler {
	private readonly didChangeAuthStateEmitter = new vscode.EventEmitter<AuthState>();
	private isAuthenticating = false;

	public readonly onDidChangeAuthState = this.didChangeAuthStateEmitter.event;

	public constructor(
		private readonly context: vscode.ExtensionContext,
		private readonly configService: ExtensionConfigService,
	) {}

	public async getAuthState(): Promise<AuthState> {
		const session = await this.getValidSession();
		return {
			isAuthenticated: session !== null,
			isAuthenticating: this.isAuthenticating,
			visitor: session?.visitor ?? null,
		};
	}

	public async getValidSession(): Promise<AuthSession | null> {
		const token = await this.context.secrets.get(VISITOR_TOKEN_SECRET_KEY);
		const visitor = this.context.globalState.get<VisitorInfo>(VISITOR_INFO_STORAGE_KEY);

		if (!token || !visitor) {
			return null;
		}

		if (!this.isTokenValid(token)) {
			await this.signOut(false);
			return null;
		}

		return { token, visitor };
	}

	public async startGoogleLogin(): Promise<void> {
		const { baseUrl, apiKey } = await this.configService.getConfig();

		if (!baseUrl || !apiKey) {
			throw new Error('Configure the Innomightlabs backend before signing in.');
		}

		this.isAuthenticating = true;
		await this.emitAuthState();

		try {
			const callbackUri = await vscode.env.asExternalUri(
				vscode.Uri.parse(`${vscode.env.uriScheme}://${this.context.extension.id}/auth-callback`),
			);
			const params = new URLSearchParams({
				api_key: apiKey,
				redirect_uri: callbackUri.toString(),
			});
			const authUrl = vscode.Uri.parse(`${baseUrl}/widget/auth/google?${params.toString()}`);
			await vscode.env.openExternal(authUrl);
		} catch (error) {
			this.isAuthenticating = false;
			await this.emitAuthState();
			throw error;
		}
	}

	public async signOut(showMessage = true): Promise<void> {
		this.isAuthenticating = false;
		await this.context.secrets.delete(VISITOR_TOKEN_SECRET_KEY);
		await this.context.globalState.update(VISITOR_INFO_STORAGE_KEY, undefined);
		await this.emitAuthState();

		if (showMessage) {
			void vscode.window.showInformationMessage('Signed out from Innomightlabs.');
		}
	}

	public async handleUri(uri: vscode.Uri): Promise<void> {
		const params = new URLSearchParams(uri.query);
		const error = params.get('error');
		if (error) {
			this.isAuthenticating = false;
			await this.emitAuthState();
			void vscode.window.showErrorMessage(`Google sign-in failed: ${error}`);
			return;
		}

		const token = params.get('token');
		const visitorId = params.get('visitor_id');
		const email = params.get('email');

		if (!token || !visitorId || !email) {
			this.isAuthenticating = false;
			await this.emitAuthState();
			void vscode.window.showErrorMessage('Google sign-in did not return the expected token data.');
			return;
		}

		const visitor: VisitorInfo = {
			visitorId,
			email,
			name: params.get('name') || email.split('@')[0],
			picture: params.get('picture'),
		};

		await this.context.secrets.store(VISITOR_TOKEN_SECRET_KEY, token);
		await this.context.globalState.update(VISITOR_INFO_STORAGE_KEY, visitor);

		this.isAuthenticating = false;
		await this.emitAuthState();
		void vscode.window.showInformationMessage(`Signed in as ${visitor.email}.`);
	}

	private isTokenValid(token: string): boolean {
		try {
			const payload = JSON.parse(Buffer.from(token.split('.')[1], 'base64').toString('utf8')) as {
				exp?: number;
			};
			if (typeof payload.exp !== 'number') {
				return false;
			}
			return Date.now() < payload.exp * 1000;
		} catch {
			return false;
		}
	}

	private async emitAuthState(): Promise<void> {
		this.didChangeAuthStateEmitter.fire(await this.getAuthState());
	}
}
