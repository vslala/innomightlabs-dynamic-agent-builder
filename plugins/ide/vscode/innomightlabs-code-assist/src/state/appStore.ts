import type { Disposable } from 'vscode';

import { initialAppState, type AppState } from './appState';

type Listener = (state: AppState) => void;

export class AppStore {
	private state: AppState = initialAppState;
	private readonly listeners = new Set<Listener>();

	public getState(): AppState {
		return this.state;
	}

	public setState(next: AppState): void {
		this.state = next;
		this.emit();
	}

	public update(updater: (state: AppState) => AppState): void {
		this.state = updater(this.state);
		this.emit();
	}

	public subscribe(listener: Listener): Disposable {
		this.listeners.add(listener);
		listener(this.state);
		return {
			dispose: () => {
				this.listeners.delete(listener);
			},
		};
	}

	private emit(): void {
		for (const listener of this.listeners) {
			listener(this.state);
		}
	}
}
