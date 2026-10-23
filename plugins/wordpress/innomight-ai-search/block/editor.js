( function ( wp ) {
	var el = wp.element.createElement;
	wp.blocks.registerBlockType( 'innomight/ai-search', {
		edit: function () {
			return el( 'div', wp.blockEditor.useBlockProps(), el( wp.serverSideRender, { block: 'innomight/ai-search' } ) );
		},
		save: function () {
			return null;
		}
	} );
}( window.wp ) );
