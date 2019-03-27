require 'rack/wwwhisper'
require File.expand_path("../rack_try_static", __FILE__)

use ::Rack::WWWhisper

use ::Rack::TryStatic,
  :root => "../build",
  :urls => ["/"],
  :try  => [".html", "index.html", "/index.html", ""]

run lambda {
  not_found_page = File.expand_path('../../build/index.html', __FILE__)
  [404, {'Content-Type' => 'text/html'}, [File.read(not_found_page)]]
}
