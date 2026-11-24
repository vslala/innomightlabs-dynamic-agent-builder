/**
 * Block-editor writing tools: ask about or rewrite selected text, and the /ai block.
 * Plain wp.* globals, so there is no build step.
 */
( function ( wp, config ) {
	'use strict';

	var el = wp.element.createElement;
	var useState = wp.element.useState;
	var useRef = wp.element.useRef;
	var useEffect = wp.element.useEffect;
	var __ = wp.i18n.__;
	var c = wp.components;

	/* ------------------------------------------------------------ streaming */

	/** Read one Server-Sent Events block and return its text or throw its error. */
	function readEvent( block ) {
		var event = '';
		var data = '';
		block.split( '\n' ).forEach( function ( line ) {
			if ( 0 === line.indexOf( 'event:' ) ) {
				event = line.slice( 6 ).trim();
			} else if ( 0 === line.indexOf( 'data:' ) ) {
				data += line.slice( 5 ).trim();
			}
		} );
		var json = {};
		try {
			json = data ? JSON.parse( data ) : {};
		} catch ( e ) {
			return '';
		}
		if ( 'error' === event ) {
			throw new Error( json.message || __( 'The assistant ran into a problem. Please try again.', 'innomight-ai-search' ) );
		}
		return 'message.delta' === event && 'string' === typeof json.text ? json.text : '';
	}

	/** POST to the write route and call onText with the full answer so far. Resolves with the answer. */
	function streamAnswer( payload, signal, onText ) {
		var answer = '';
		var take = function ( block ) {
			answer += readEvent( block );
			onText( answer );
		};
		return fetch( config.url, {
			method: 'POST',
			credentials: 'same-origin',
			signal: signal,
			headers: { 'Content-Type': 'application/json', 'X-WP-Nonce': config.nonce },
			body: JSON.stringify( payload )
		} ).then( function ( response ) {
			if ( ! response.ok ) {
				return response.json().catch( function () {
					return {};
				} ).then( function ( error ) {
					throw new Error( error.message || __( 'The assistant is temporarily unavailable.', 'innomight-ai-search' ) );
				} );
			}
			if ( ! response.body ) {
				return response.text().then( function ( text ) {
					text.replace( /\r\n/g, '\n' ).split( '\n\n' ).forEach( take );
				} );
			}
			var reader = response.body.getReader();
			var decoder = new TextDecoder();
			var buffer = '';
			var pump = function () {
				return reader.read().then( function ( result ) {
					if ( result.done ) {
						return;
					}
					buffer += decoder.decode( result.value, { stream: true } ).replace( /\r\n/g, '\n' );
					var end;
					while ( -1 !== ( end = buffer.indexOf( '\n\n' ) ) ) {
						take( buffer.slice( 0, end ) );
						buffer = buffer.slice( end + 2 );
					}
					return pump();
				} );
			};
			return pump();
		} ).then( function () {
			return answer.trim();
		} );
	}

	/** State for one running request: { text, status: idle|working|done|error, error }. */
	function useWriter() {
		var state = useState( { text: '', status: 'idle', error: '' } );
		var setState = state[ 1 ];
		var controller = useRef( null );
		useEffect( function () {
			return function () {
				if ( controller.current ) {
					controller.current.abort();
				}
			};
		}, [] );
		var run = function ( payload ) {
			if ( controller.current ) {
				controller.current.abort();
			}
			var mine = new AbortController();
			controller.current = mine;
			setState( { text: '', status: 'working', error: '' } );
			streamAnswer( payload, mine.signal, function ( text ) {
				setState( { text: text, status: 'working', error: '' } );
			} ).then( function ( text ) {
				setState( { text: text, status: 'done', error: '' } );
			} ).catch( function ( error ) {
				if ( 'AbortError' !== error.name ) {
					setState( { text: '', status: 'error', error: error.message } );
				}
			} );
		};
		var reset = function () {
			if ( controller.current ) {
				controller.current.abort();
			}
			setState( { text: '', status: 'idle', error: '' } );
		};
		return { state: state[ 0 ], run: run, reset: reset };
	}

	/* ------------------------------------------------------------ article context */

	function plainText( html ) {
		var box = document.createElement( 'div' );
		box.innerHTML = html;
		return ( box.textContent || '' ).trim();
	}

	/** The post title, or '' where there is none (for example the site editor). */
	function postTitle() {
		var editor = wp.data.select( 'core/editor' );
		return editor && editor.getEditedPostAttribute ? String( editor.getEditedPostAttribute( 'title' ) || '' ) : '';
	}

	/** Text of up to three blocks before the one holding clientId (and that block too, if asked). */
	function textBefore( clientId, includeCurrent ) {
		var store = wp.data.select( 'core/block-editor' );
		var root = store.getBlockHierarchyRootClientId( clientId );
		var blocks = store.getBlocks();
		var index = blocks.findIndex( function ( block ) {
			return block.clientId === root;
		} );
		if ( -1 === index ) {
			return '';
		}
		var text = blocks.slice( Math.max( 0, index - 3 ), index + ( includeCurrent ? 1 : 0 ) ).map( function ( block ) {
			return plainText( wp.blocks.getBlockContent( block ) );
		} ).filter( Boolean ).join( '\n\n' );
		return text.slice( -4000 );
	}

	var MERMAID_START = /^(flowchart|graph|sequenceDiagram|classDiagram|stateDiagram|erDiagram|gantt|pie|journey|mindmap|timeline|gitGraph|quadrantChart|xychart)\b/;

	/**
	 * Markdown conversion drops the language of a fenced block, so a Mermaid diagram arrives as a plain
	 * code block. Use a theme's Mermaid block (it previews live in the editor) when one is registered;
	 * otherwise mark the code block with the language-mermaid class that themes and plugins look for.
	 */
	function markMermaid( blocks ) {
		return blocks.map( function ( block ) {
			var source = 'core/code' === block.name ? plainText( block.attributes.content || '' ) : '';
			if ( ! MERMAID_START.test( source ) ) {
				return block;
			}
			if ( wp.blocks.getBlockType( 'bma/mermaid' ) ) {
				return wp.blocks.createBlock( 'bma/mermaid', { source: source } );
			}
			return wp.blocks.cloneBlock( block, { className: 'language-mermaid' } );
		} );
	}

	/* ------------------------------------------------------------ shared pieces */

	function Result( props ) {
		var writer = props.writer.state;
		if ( 'error' === writer.status ) {
			return el( c.Notice, { status: 'error', isDismissible: false }, writer.error );
		}
		if ( 'idle' === writer.status ) {
			return null;
		}
		return el( 'div', { className: 'innomight-ai__result' },
			writer.text || el( 'span', { className: 'innomight-ai__waiting' }, el( c.Spinner ), __( 'Thinking…', 'innomight-ai-search' ) )
		);
	}

	function copy( text ) {
		if ( navigator.clipboard ) {
			navigator.clipboard.writeText( text );
		}
	}

	/* ------------------------------------------------------------ selection tools */

	var REWRITES = [
		[ 'improve', __( 'Improve writing', 'innomight-ai-search' ) ],
		[ 'grammar', __( 'Fix grammar', 'innomight-ai-search' ) ],
		[ 'shorten', __( 'Shorten', 'innomight-ai-search' ) ],
		[ 'expand', __( 'Expand', 'innomight-ai-search' ) ],
		[ 'friendly', __( 'Friendlier', 'innomight-ai-search' ) ],
		[ 'professional', __( 'More professional', 'innomight-ai-search' ) ]
	];

	/** The popover opened from the toolbar. `picked` is a snapshot of the selection when it opened. */
	function SelectionPanel( props ) {
		var picked = props.picked;
		var writer = useWriter();
		var mode = useState( 'ask' );
		var prompt = useState( '' );
		var done = 'done' === writer.state.status;
		var working = 'working' === writer.state.status;

		var send = function ( payload ) {
			writer.run( Object.assign( { selection: picked.text, before: picked.before, title: picked.title }, payload ) );
		};
		var switchTo = function ( next ) {
			writer.reset();
			mode[ 1 ]( next );
		};

		return el( c.Popover, { anchor: props.anchor, onClose: props.onClose, placement: 'bottom-start', className: 'innomight-ai__popover', focusOnMount: 'firstElementChild' },
			el( 'div', { className: 'innomight-ai__panel' },
				el( 'div', { className: 'innomight-ai__tabs' },
					[ [ 'ask', __( 'Ask', 'innomight-ai-search' ) ], [ 'rewrite', __( 'Rewrite', 'innomight-ai-search' ) ] ].map( function ( tab ) {
						return el( c.Button, { key: tab[ 0 ], variant: mode[ 0 ] === tab[ 0 ] ? 'primary' : 'tertiary', onClick: function () {
							switchTo( tab[ 0 ] );
						} }, tab[ 1 ] );
					} )
				),
				el( 'blockquote', { className: 'innomight-ai__quote' }, picked.text.length > 160 ? picked.text.slice( 0, 160 ) + '…' : picked.text ),
				'ask' === mode[ 0 ] && el( 'div', null,
					el( c.TextareaControl, {
						label: __( 'What do you want to know about this?', 'innomight-ai-search' ),
						value: prompt[ 0 ],
						rows: 2,
						placeholder: __( 'For example: find sources, explain it, or give an example', 'innomight-ai-search' ),
						onChange: prompt[ 1 ]
					} ),
					el( c.Button, { variant: 'primary', disabled: working || '' === prompt[ 0 ].trim(), onClick: function () {
						send( { mode: 'ask', prompt: prompt[ 0 ] } );
					} }, __( 'Ask', 'innomight-ai-search' ) )
				),
				'rewrite' === mode[ 0 ] && el( 'div', { className: 'innomight-ai__actions' },
					REWRITES.map( function ( action ) {
						return el( c.Button, { key: action[ 0 ], variant: 'secondary', disabled: working, onClick: function () {
							send( { mode: 'rewrite', action: action[ 0 ] } );
						} }, action[ 1 ] );
					} )
				),
				el( Result, { writer: writer } ),
				done && el( 'div', { className: 'innomight-ai__buttons' },
					'rewrite' === mode[ 0 ]
						? el( c.Button, { variant: 'primary', onClick: function () {
							props.onReplace( writer.state.text );
						} }, __( 'Replace selection', 'innomight-ai-search' ) )
						: el( c.Button, { variant: 'primary', onClick: function () {
							props.onInsertAfter( writer.state.text );
						} }, __( 'Insert after', 'innomight-ai-search' ) ),
					el( c.Button, { variant: 'secondary', onClick: function () {
						copy( writer.state.text );
					} }, __( 'Copy', 'innomight-ai-search' ) ),
					el( c.Button, { variant: 'tertiary', onClick: props.onClose }, __( 'Discard', 'innomight-ai-search' ) )
				)
			)
		);
	}

	var formatName = 'innomight/ai';
	var formatSettings = {
		title: __( 'Innomight AI', 'innomight-ai-search' ),
		tagName: 'span',
		className: 'innomight-ai-selection', // Never applied: the button only opens the panel.
		edit: function ( props ) {
			var value = props.value;
			var open = useState( null );
			var anchor = wp.richText.useAnchor( { editableContentElement: props.contentRef.current, settings: formatSettings } );
			var picked = open[ 0 ];

			var openPanel = function () {
				var selected = wp.data.select( 'core/block-editor' ).getSelectedBlockClientId();
				open[ 1 ]( {
					value: value,
					text: wp.richText.getTextContent( wp.richText.slice( value ) ),
					before: selected ? textBefore( selected, true ) : '',
					title: postTitle()
				} );
			};
			var replace = function ( text, atEnd ) {
				var at = atEnd ? Object.assign( {}, picked.value, { start: picked.value.end } ) : picked.value;
				props.onChange( wp.richText.insert( at, atEnd ? ' ' + text : text ) );
				open[ 1 ]( null );
			};

			return el( wp.element.Fragment, null,
				el( wp.blockEditor.RichTextToolbarButton, {
					icon: 'admin-site-alt3',
					title: __( 'Ask or rewrite with AI', 'innomight-ai-search' ),
					onClick: openPanel,
					isActive: !! picked,
					disabled: wp.richText.isCollapsed( value )
				} ),
				picked && el( SelectionPanel, {
					anchor: anchor,
					picked: picked,
					onClose: function () {
						open[ 1 ]( null );
					},
					onReplace: function ( text ) {
						replace( text, false );
					},
					onInsertAfter: function ( text ) {
						replace( text, true );
					}
				} )
			);
		}
	};
	wp.richText.registerFormatType( formatName, formatSettings );

	/* ------------------------------------------------------------ the /ai block */

	function WriterEdit( props ) {
		var writer = useWriter();
		var prompt = useState( '' );
		var length = useState( 'paragraph' );
		var working = 'working' === writer.state.status;
		var done = 'done' === writer.state.status;

		var write = function () {
			writer.run( {
				mode: 'generate',
				prompt: prompt[ 0 ],
				length: length[ 0 ],
				before: textBefore( props.clientId, false ),
				title: postTitle()
			} );
		};
		/** Turn the answer into real blocks: Markdown becomes headings, lists and paragraphs. */
		var insert = function () {
			var blocks = markMermaid( wp.blocks.pasteHandler( { plainText: writer.state.text, mode: 'BLOCKS' } ) );
			wp.data.dispatch( 'core/block-editor' ).replaceBlocks( props.clientId, blocks.length ? blocks : wp.blocks.createBlock( 'core/paragraph', { content: writer.state.text } ) );
		};

		return el( 'div', wp.blockEditor.useBlockProps( { className: 'innomight-ai__block' } ),
			el( c.TextareaControl, {
				label: __( 'Describe what to write', 'innomight-ai-search' ),
				value: prompt[ 0 ],
				rows: 3,
				placeholder: __( 'For example: explain why small teams should adopt AI agents, with one concrete example', 'innomight-ai-search' ),
				onChange: prompt[ 1 ]
			} ),
			el( c.SelectControl, {
				label: __( 'Length', 'innomight-ai-search' ),
				value: length[ 0 ],
				options: [
					{ value: 'sentence', label: __( 'A sentence', 'innomight-ai-search' ) },
					{ value: 'paragraph', label: __( 'A paragraph', 'innomight-ai-search' ) },
					{ value: 'section', label: __( 'A section', 'innomight-ai-search' ) }
				],
				onChange: length[ 1 ]
			} ),
			el( Result, { writer: writer } ),
			el( 'div', { className: 'innomight-ai__buttons' },
				done && el( c.Button, { variant: 'primary', onClick: insert }, __( 'Insert', 'innomight-ai-search' ) ),
				el( c.Button, { variant: done ? 'secondary' : 'primary', disabled: working || '' === prompt[ 0 ].trim(), onClick: write }, done ? __( 'Try again', 'innomight-ai-search' ) : __( 'Write', 'innomight-ai-search' ) ),
				el( c.Button, { variant: 'tertiary', onClick: function () {
					wp.data.dispatch( 'core/block-editor' ).removeBlock( props.clientId );
				} }, __( 'Discard', 'innomight-ai-search' ) )
			)
		);
	}

	// Title, icon and keywords come from blocks/ai-write/block.json.
	wp.blocks.registerBlockType( 'innomight/ai-write', {
		edit: WriterEdit,
		save: function () {
			return null;
		}
	} );
}( window.wp, window.innomightWrite ) );
