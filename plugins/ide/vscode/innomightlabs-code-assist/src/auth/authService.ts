import * as vscode from 'vscode';

import type { ExtensionConfigService } from '../config/extensionConfigService';

const VISITOR_TOKEN_SECRET_KEY = 'innomightlabs.visitorToken';
const VISITOR_REFRESH_TOKEN_SECRET_KEY = 'innomightlabs.visitorRefreshToken';
const VISITOR_INFO_STORAGE_KEY = 'innomightlabs.visitorInfo';
const AUTHENTICATION_TIMEOUT_MS = 30_000;

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
	private authenticationTimeout: ReturnType<typeof setTimeout> | undefined;
	private refreshSessionPromise: Promise<AuthSession | null> | null = null;

	public readonly onDidChangeAuthState = this.didChangeAuthStateEmitter.event;

	public constructor(
		private readonly context: vscode.ExtensionContext,
		private readonly configService: ExtensionConfigService,
	) {
		this.context.subscriptions.push({
			dispose: () => this.clearAuthenticationTimeout(),
		});
	}

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
			return this.refreshSession();
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
		this.startAuthenticationTimeout();

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
			this.clearAuthenticationTimeout();
			await this.emitAuthState();
			throw error;
		}
	}

	public async signOut(showMessage = true): Promise<void> {
		this.isAuthenticating = false;
		this.clearAuthenticationTimeout();
		await this.context.secrets.delete(VISITOR_TOKEN_SECRET_KEY);
		await this.context.secrets.delete(VISITOR_REFRESH_TOKEN_SECRET_KEY);
		await this.context.globalState.update(VISITOR_INFO_STORAGE_KEY, undefined);
		await this.emitAuthState();

		if (showMessage) {
			void vscode.window.showInformationMessage('Signed out from Innomightlabs.');
		}
	}

	public async refreshSession(): Promise<AuthSession | null> {
		if (this.refreshSessionPromise) {
			return this.refreshSessionPromise;
		}

		this.refreshSessionPromise = this.refreshSessionInternal().finally(() => {
			this.refreshSessionPromise = null;
		});

		return this.refreshSessionPromise;
	}

	public async handleUri(uri: vscode.Uri): Promise<void> {
		const params = new URLSearchParams(uri.query);
		const error = params.get('error');
		if (error) {
			this.isAuthenticating = false;
			this.clearAuthenticationTimeout();
			await this.emitAuthState();
			void vscode.window.showErrorMessage(`Google sign-in failed: ${error}`);
			return;
		}

		const token = params.get('token');
		const refreshToken = params.get('refresh_token');
		const visitorId = params.get('visitor_id');
		const email = params.get('email');

		if (!token || !visitorId || !email) {
			this.isAuthenticating = false;
			this.clearAuthenticationTimeout();
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
		if (refreshToken) {
			await this.context.secrets.store(VISITOR_REFRESH_TOKEN_SECRET_KEY, refreshToken);
		}
		await this.context.globalState.update(VISITOR_INFO_STORAGE_KEY, visitor);

		this.isAuthenticating = false;
		this.clearAuthenticationTimeout();
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

	private async refreshSessionInternal(): Promise<AuthSession | null> {
		const refreshToken = await this.context.secrets.get(VISITOR_REFRESH_TOKEN_SECRET_KEY);
		const storedVisitor = this.context.globalState.get<VisitorInfo>(VISITOR_INFO_STORAGE_KEY);

		if (!refreshToken || !storedVisitor) {
			await this.signOut(false);
			return null;
		}

		const { baseUrl, apiKey } = await this.configService.getConfig();
		if (!baseUrl || !apiKey) {
			await this.signOut(false);
			return null;
		}

		try {
			const response = await fetch(`${baseUrl}/widget/auth/refresh`, {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					'x-api-key': apiKey,
				},
				body: JSON.stringify({ refresh_token: refreshToken }),
			});

			if (!response.ok) {
				await this.signOut(false);
				return null;
			}

			const payload = (await response.json()) as WidgetRefreshResponse;
			const token = this.extractAccessToken(payload);
			if (!token || !this.isTokenValid(token)) {
				await this.signOut(false);
				return null;
			}

			const visitor = this.extractVisitor(payload) ?? storedVisitor;
			await this.context.secrets.store(VISITOR_TOKEN_SECRET_KEY, token);

			if (typeof payload.refresh_token === 'string' && payload.refresh_token.length > 0) {
				await this.context.secrets.store(VISITOR_REFRESH_TOKEN_SECRET_KEY, payload.refresh_token);
			}

			await this.context.globalState.update(VISITOR_INFO_STORAGE_KEY, visitor);
			await this.emitAuthState();

			return { token, visitor };
		} catch {
			await this.signOut(false);
			return null;
		}
	}

	private startAuthenticationTimeout(): void {
		this.clearAuthenticationTimeout();
		this.authenticationTimeout = setTimeout(() => {
			if (!this.isAuthenticating) {
				return;
			}

			this.isAuthenticating = false;
			void this.emitAuthState();
			void vscode.window.showWarningMessage('Google sign-in timed out. You can try signing in again.');
		}, AUTHENTICATION_TIMEOUT_MS);
	}

	private clearAuthenticationTimeout(): void {
		if (!this.authenticationTimeout) {
			return;
		}

		clearTimeout(this.authenticationTimeout);
		this.authenticationTimeout = undefined;
	}

	private extractAccessToken(payload: WidgetRefreshResponse): string | null {
		if (typeof payload.access_token === 'string' && payload.access_token.length > 0) {
			return payload.access_token;
		}

		if (typeof payload.token === 'string' && payload.token.length > 0) {
			return payload.token;
		}

		return null;
	}

	private extractVisitor(payload: WidgetRefreshResponse): VisitorInfo | null {
		const visitor = payload.visitor;
		if (!visitor || typeof visitor !== 'object') {
			return null;
		}

		const visitorId = typeof visitor.visitor_id === 'string'
			? visitor.visitor_id
			: visitor.visitorId;
		if (typeof visitorId !== 'string' || typeof visitor.email !== 'string') {
			return null;
		}

		return {
			visitorId,
			email: visitor.email,
			name: typeof visitor.name === 'string' && visitor.name.length > 0
				? visitor.name
				: visitor.email.split('@')[0],
			picture: typeof visitor.picture === 'string' && visitor.picture.length > 0
				? visitor.picture
				: null,
		};
	}

	private async emitAuthState(): Promise<void> {
		this.didChangeAuthStateEmitter.fire(await this.getAuthState());
	}
}

type WidgetRefreshResponse = {
	access_token?: unknown;
	token?: unknown;
	refresh_token?: unknown;
	visitor?: {
		visitor_id?: unknown;
		visitorId?: unknown;
		email?: unknown;
		name?: unknown;
		picture?: unknown;
	};
};
