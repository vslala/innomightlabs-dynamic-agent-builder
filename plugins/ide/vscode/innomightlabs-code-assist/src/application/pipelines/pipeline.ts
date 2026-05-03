export type PipelineContext = {
	halted?: boolean;
};

export interface PipelineStep<TContext extends PipelineContext> {
	execute(context: TContext): Promise<void>;
}

export class Pipeline<TContext extends PipelineContext> {
	public constructor(private readonly steps: PipelineStep<TContext>[]) {}

	public async run(context: TContext): Promise<TContext> {
		for (const step of this.steps) {
			if (context.halted) {
				break;
			}

			await step.execute(context);
		}

		return context;
	}
}
