/* Innomight AI Search: streams a follow-up conversation from your Innomight Labs agent. No dependencies. */
( function () {
	'use strict';

	/* Answers are model text: escape everything first, then add only the markup we allow. */
	function esc( s ) {
		return String( s ).replace( /&/g, '&amp;' ).replace( /</g, '&lt;' ).replace( />/g, '&gt;' ).replace( /"/g, '&quot;' ).replace( /'/g, '&#39;' );
	}
	function link( url, text ) {
		var local = url.indexOf( location.origin ) === 0;
		return '<a href="' + url + '"' + ( local ? '' : ' target="_blank" rel="noopener noreferrer"' ) + '>' + text + '</a>';
	}
	function inline( s ) {
		return s
			.replace( /`([^`\n]+)`/g, '<code>$1</code>' )
			.replace( /\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>' )
			.replace( /(^|[\s(])\*([^*\s][^*\n]*)\*(?=[\s).,;:!?]|$)/g, '$1<em>$2</em>' )
			.replace( /\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)/g, function ( m, t, u ) { return link( u, t ); } )
			.replace( /(^|[\s(])(https?:\/\/[^\s<)]*[^\s<).,;:!?])/g, function ( m, p, u ) { return p + link( u, u ); } );
	}
	function markdown( src ) {
		var out = '';
		String( src ).split( '```' ).forEach( function ( part, i ) {
			if ( i % 2 ) { // Fenced code. An unclosed fence is still code while streaming.
				var nl = part.indexOf( '\n' );
				out += '<pre><code>' + esc( ( nl < 0 ? '' : part.slice( nl + 1 ) ).replace( /\n$/, '' ) ) + '</code></pre>';
				return;
			}
			var list = '', para = [];
			var flushPara = function () { if ( para.length ) { out += '<p>' + inline( esc( para.join( ' ' ) ) ) + '</p>'; para = []; } };
			var flushList = function () { if ( list ) { out += '</' + list + '>'; list = ''; } };
			part.split( '\n' ).forEach( function ( line ) {
				var h = /^\s{0,3}#{1,4}\s+(.*)$/.exec( line ), li = /^\s*(?:([-*•])|(\d+)[.)])\s+(.*)$/.exec( line );
				if ( h ) { flushPara(); flushList(); out += '<h4>' + inline( esc( h[1] ) ) + '</h4>'; }
				else if ( li ) {
					flushPara();
					var want = li[2] ? 'ol' : 'ul';
					if ( list !== want ) { flushList(); out += '<' + want + '>'; list = want; }
					out += '<li>' + inline( esc( li[3] ) ) + '</li>';
				}
				else if ( ! line.trim() ) { flushPara(); flushList(); }
				else { flushList(); para.push( line.trim() ); }
			} );
			flushPara(); flushList();
		} );
		return out;
	}

	function visitorId() {
		var key = 'innomight-search-visitor', v = '';
		try { v = localStorage.getItem( key ) || ''; } catch ( e ) {}
		if ( ! /^[A-Za-z0-9_-]{8,64}$/.test( v ) ) {
			v = ( window.crypto && crypto.randomUUID ) ? crypto.randomUUID() : ( Date.now().toString( 36 ) + Math.random().toString( 36 ).slice( 2, 12 ) );
			try { localStorage.setItem( key, v ); } catch ( e ) {}
		}
		return v;
	}

	function init( root ) {
		var endpoint = root.getAttribute( 'data-endpoint' ), search = root.getAttribute( 'data-search' ) || '', text = {};
		try { text = JSON.parse( root.getAttribute( 'data-i18n' ) || '{}' ); } catch ( e ) {}
		var thread = root.querySelector( '.innomight-search__thread' ), form = root.querySelector( 'form' ),
			input = form.querySelector( 'input' ), send = form.querySelector( 'button' ), sug = root.querySelector( '.innomight-search__sug' );
		var ckey = 'innomight-search-conv:' + location.hostname + ':' + search, conv = '', busy = false;
		try { conv = sessionStorage.getItem( ckey ) || ''; } catch ( e ) {}
		function setConv( id ) {
			conv = id || '';
			try { conv ? sessionStorage.setItem( ckey, conv ) : sessionStorage.removeItem( ckey ); } catch ( e ) {}
		}
		function bubble( role ) {
			var m = document.createElement( 'div' ), b = document.createElement( 'div' );
			m.className = 'innomight-search__msg is-' + role; b.className = 'innomight-search__body';
			m.appendChild( b ); thread.hidden = false; thread.appendChild( m );
			try { m.scrollIntoView( { block: 'nearest', behavior: 'smooth' } ); } catch ( e ) {}
			return b;
		}
		function ask( q ) {
			q = ( q || '' ).trim();
			if ( ! q || busy ) { return; }
			busy = true; input.value = ''; input.disabled = true; send.disabled = true;
			if ( sug ) { sug.hidden = true; }
			bubble( 'user' ).textContent = q;
			var body = bubble( 'bot' ), answer = '', frame = 0;
			body.innerHTML = '<span class="innomight-search__status">' + esc( text.thinking || 'Thinking…' ) + '</span><span class="innomight-search__cursor"></span>';
			function paint() { frame = 0; body.innerHTML = markdown( answer ) + '<span class="innomight-search__cursor"></span>'; }
			function finish( failure ) {
				if ( frame ) { cancelAnimationFrame( frame ); }
				busy = false; input.disabled = false; send.disabled = false;
				body.innerHTML = failure ? '<p class="innomight-search__error">' + esc( failure ) + '</p>' : markdown( answer );
				input.focus();
			}
			function handle( name, data ) {
				if ( name === 'conversation' && data.conversation_id ) { setConv( data.conversation_id ); }
				else if ( name === 'message.delta' && typeof data.text === 'string' ) { answer += data.text; if ( ! frame ) { frame = requestAnimationFrame( paint ); } }
				else if ( name === 'error' ) { if ( data.code === 'conversation_lost' ) { setConv( '' ); } throw new Error( data.message || text.error ); }
			}
			fetch( endpoint, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
				body: JSON.stringify( { question: q, visitor: visitorId(), conversation_id: conv, search: search } )
			} ).then( function ( res ) {
				if ( ! res.ok ) { return res.json().then( function ( j ) { throw new Error( ( j && j.message ) || text.error ); }, function () { throw new Error( text.error ); } ); }
				var reader = res.body.getReader(), decoder = new TextDecoder(), buffer = '';
				function pump() {
					return reader.read().then( function ( r ) {
						if ( r.done ) { return; }
						buffer += decoder.decode( r.value, { stream: true } ).replace( /\r\n/g, '\n' );
						var i;
						while ( ( i = buffer.indexOf( '\n\n' ) ) >= 0 ) {
							var block = buffer.slice( 0, i ), name = '', data = '';
							buffer = buffer.slice( i + 2 );
							block.split( '\n' ).forEach( function ( l ) {
								if ( l.indexOf( 'event:' ) === 0 ) { name = l.slice( 6 ).trim(); }
								else if ( l.indexOf( 'data:' ) === 0 ) { data += l.slice( 5 ).trim(); }
							} );
							if ( ! name ) { continue; }
							var json = {}; try { json = data ? JSON.parse( data ) : {}; } catch ( e ) {}
							handle( name, json );
						}
						return pump();
					} );
				}
				return pump();
			} ).then( function () { finish( answer ? '' : ( text.error || 'Something went wrong.' ) ); } )
				.catch( function ( e ) { finish( e.message || text.error ); } );
		}
		form.addEventListener( 'submit', function ( e ) { e.preventDefault(); ask( input.value ); } );
		if ( sug ) { sug.querySelectorAll( 'button' ).forEach( function ( b ) { b.addEventListener( 'click', function () { ask( b.textContent ); } ); } ); }
	}

	function boot() { document.querySelectorAll( '[data-innomight-search]' ).forEach( init ); }
	if ( document.readyState === 'loading' ) { document.addEventListener( 'DOMContentLoaded', boot ); } else { boot(); }
}() );
