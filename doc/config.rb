# Unique header generation
require './lib/unique_head.rb'

# Markdown
set :markdown_engine, :redcarpet
set :markdown,
    fenced_code_blocks: true,
    smartypants: true,
    disable_indented_code_blocks: true,
    prettify: true,
    strikethrough: true,
    tables: true,
    with_toc_data: true,
    no_intra_emphasis: true,
    renderer: UniqueHeadCounter

# Assets
set :css_dir, 'stylesheets'
set :js_dir, 'javascripts'
set :images_dir, 'images'
set :fonts_dir, 'fonts'

# Activate the syntax highlighter
activate :syntax
ready do
  require './lib/multilang.rb'
end

activate :sprockets

activate :autoprefixer do |config|
  config.browsers = ['last 2 version', 'Firefox ESR']
  config.cascade  = false
  config.inline   = true
end

# Github pages require relative links
activate :relative_assets
set :relative_links, true

# Build Configuration
configure :build do
  # If you're having trouble with Middleman hanging, commenting
  # out the following two lines has been known to help
  activate :minify_css
  activate :minify_javascript
  # activate :relative_assets
  # activate :asset_hash
  # activate :gzip
end

# Deploy Configuration
# If you want Middleman to listen on a different port, you can set that below
set :port, 4567

helpers do
  require './lib/toc_data.rb'
end

# Import static files for deploying to the site
import_file File.join( __dir__, 'files', 'walkthrough/atombot.py'), 'walkthrough/atombot.py'
import_file File.join( __dir__, 'files', 'walkthrough/Dockerfile'), 'walkthrough/Dockerfile'
import_file File.join( __dir__, 'files', 'walkthrough/docker-compose.yml'), 'walkthrough/docker-compose.yml'
import_file File.join( __dir__, 'files', 'walkthrough/launch.sh'), 'walkthrough/launch.sh'
import_file File.join( __dir__, 'files', 'docker/Dockerfile'), 'docker/Dockerfile'
import_file File.join( __dir__, 'files', 'docker-compose/docker-compose.yml'), 'docker-compose/docker-compose.yml'
import_file File.join( __dir__, 'files', 'real-sense-demo.zip'), 'real-sense-demo.zip'
