#NOTE: See Clang.jl on github for examples/explanation
#This script wraps some but not all of the atom and redis libraries (but maybe it's enough of the api that it's usable already)
#Currently need these manual changes after generation:
#    struct element → struct Element in libatom_common.jl
#    Ptr{element} → Ptr{Element} in libatom_api.jl

using Clang

atom_dir = "/home/cody/src/atom"

# LIBATOM_HEADERS are those headers to be wrapped.
const LIBATOM_INCLUDE = joinpath(atom_dir, "languages", "c", "inc") |> normpath
const LIBREDIS_INCLUDE = joinpath(atom_dir, "languages", "c", "third-party", "hiredis", "hiredis") |> normpath
const STD_INCLUDE = "/usr/include"
const OTHER_INCLUDE = "/usr/lib/gcc/x86_64-linux-gnu/7.4.0/include"
atom_headers = [joinpath(LIBATOM_INCLUDE, header) for header in readdir(LIBATOM_INCLUDE) if endswith(header, ".h")]
redis_headers = [joinpath(LIBREDIS_INCLUDE, header) for header in readdir(LIBREDIS_INCLUDE) if endswith(header, ".h")]
const LIBATOM_HEADERS = vcat(atom_headers, redis_headers)

clang_args = ["-I", joinpath(LIBATOM_INCLUDE, ".."),
	      "-I", STD_INCLUDE,
	      "-I", OTHER_INCLUDE]

wc = init(; headers = LIBATOM_HEADERS,
            output_file = joinpath(@__DIR__, "libatom_api.jl"),
            common_file = joinpath(@__DIR__, "libatom_common.jl"),
	    clang_includes = [LIBATOM_INCLUDE],
            clang_args = clang_args,
            header_wrapped = (root, current)-> root == current,
            header_library = x->"libatom",
            clang_diagnostics = true,
            )

wc.options.wrap_structs=false

run(wc)
