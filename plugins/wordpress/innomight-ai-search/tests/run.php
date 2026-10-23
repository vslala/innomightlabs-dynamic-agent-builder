<?php
/** Run the dependency-free suite: php tests/run.php */
error_reporting( E_ALL );
set_error_handler( static function ( int $severity, string $message, string $file, int $line ): bool {
	if ( ! ( error_reporting() & $severity ) ) { return false; }
	throw new ErrorException( $message, 0, $severity, $file, $line );
} );
require_once __DIR__ . '/bootstrap.php';

$passed = 0;
$failed = 0;
$files  = glob( __DIR__ . '/*.test.php' );
sort( $files );
foreach ( $files as $file ) {
	foreach ( require $file as $name => $test ) {
		reset_wp_test();
		try {
			$test();
			++$passed;
			echo "PASS $name\n";
		} catch ( Throwable $error ) {
			++$failed;
			echo "FAIL $name\n  " . $error->getMessage() . "\n  " . $error->getFile() . ':' . $error->getLine() . "\n";
		}
	}
}
echo "\n$passed passed, $failed failed (" . ( $passed + $failed ) . " total)\n";
exit( $failed > 0 || 0 === $passed ? 1 : 0 );
