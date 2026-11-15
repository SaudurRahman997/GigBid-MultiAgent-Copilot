// SYNTHETIC sample code for GigBid persona fullstack. provenance: personas@228603469f77
<?php
// Register an editable "case study" block for the marketing team.
add_action('init', function () {
    register_block_type(__DIR__ . '/blocks/case-study', [
        'render_callback' => fn($attrs) => sprintf(
            '<section class="case"><h3>%s</h3><p>%s</p></section>',
            esc_html($attrs['title'] ?? ''), esc_html($attrs['summary'] ?? '')
        ),
    ]);
});
