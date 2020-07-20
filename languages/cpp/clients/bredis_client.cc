#include <iostream>
#include <chrono>
#include <string>
#include <fstream>
#include <vector>

#include <bredis/Connection.hpp>
#include <bredis/Extract.hpp>
#include <bredis/MarkerHelpers.hpp>
#include <boost/asio.hpp>
#include <boost/algorithm/string.hpp>



template <typename Iterator>
struct array_extractor : public boost::static_visitor<std::string> {
    template <typename T> std::string operator()(const T & /*value*/) const { return ""; }

    std::string operator()(const bredis::markers::array_holder_t<Iterator> &value) const {
        std::string result;
        for(auto& item: value.elements) {
            auto* str = boost::get<bredis::markers::string_t<Iterator>>(&item);
            if (str) {
                std::string copy{str->from, str->to};
                result += copy;
            }
        }
        return result;
    }
};

template <typename Iterator>
struct error_extractor : public boost::static_visitor<std::string> {
    template <typename T> std::string operator() (const T & /*value*/) const {return "";}

    std::string operator()(const bredis::markers::error_t<Iterator> &value) const {     
        std::string error;
        auto str = value.string;
        std::string copy{str.from, str.to};
        error += copy;
        return error;
    }
};

int main(){
    // log file setup here
    std::ofstream bredis_logfile;
    bredis_logfile.open("bredis_unix.log", std::ios_base::app);
    bredis_logfile << "----- LOGGING AT: " + 
        std::to_string(std::chrono::duration_cast<std::chrono::milliseconds>
            (std::chrono::system_clock::now().time_since_epoch()).count()) + "-----\n";
    
    bredis_logfile << "xadd (ms), xadd read (ms), xadd err check (ms), xrange (ms), xrange read (ms), xrange err check (ms), xrange err check custom (ms) \n";

    //for timing
    std::vector<std::string> xadd_times;
    std::vector<std::string> xadd_read_times;
    std::vector<std::string> xadd_extract_times;
    std::vector<std::string> xrange_times;
    std::vector<std::string> xrange_read_times;
    std::vector<std::string> xrange_extract_times;
    std::vector<std::string> xrange_extract_times1;
 
    int iters = 100;

    using Buffer = boost::asio::streambuf;
    using Iterator = typename bredis::to_iterator<Buffer>::iterator_t;
    
    boost::asio::io_context ioserv;

    /* unix socket here */
    using socket_t = boost::asio::local::stream_protocol::socket;
    using next_layer_t = socket_t;

    boost::asio::local::stream_protocol::endpoint end_point("/shared/redis.sock");
    socket_t sock(ioserv);
    sock.connect(end_point);
    
    //using socket_t = boost::asio::ip::tcp::socket;
    //using endpoint_t = boost::asio::ip::tcp::endpoint;
    //using next_layer_t = socket_t;
    
    //create socket & connect to endpoint
    /* auto ip_address = boost::asio::ip::address::from_string("172.20.0.2");
    auto port = boost::lexical_cast<std::uint16_t>(6379);
    boost::asio::ip::tcp::endpoint end_point(ip_address, port);
    socket_t socket(ioserv, end_point.protocol());
    socket.connect(end_point);
 */
    std::cout<<"Redis client is connected!"<<std::endl;
    
    //wrap socket in bredis connection
    bredis::Connection<next_layer_t> bredis_con(std::move(sock));

    //create buffer
    Buffer tx_buff, rx_buff;

    //read image in
    std::ifstream img_file("./clients/data/nasa1.jpg", std::ios::binary);
    std::string img_binary = std::string((std::istreambuf_iterator<char>(img_file)), std::istreambuf_iterator<char>());

    //start write timer
    std::chrono::time_point<std::chrono::high_resolution_clock> start_w = std::chrono::high_resolution_clock::now();

    for(int i = 0; i < iters; i++){
        //---- time XADD start
        std::string key = "nasa_pic" + std::to_string(i);
        std::chrono::time_point<std::chrono::high_resolution_clock> start_w0 = std::chrono::high_resolution_clock::now();
        boost::system::error_code xadd_err;
        bredis_con.write(bredis::single_command_t{ "XADD", "bredis", "*", key, img_binary }, xadd_err);
        if (xadd_err){
            std::cout<<"ERROR: " <<xadd_err.message()<<std::endl;
        }

        std::chrono::time_point<std::chrono::high_resolution_clock> stop_w0 = std::chrono::high_resolution_clock::now();
        auto dur_w0 = std::chrono::duration_cast<std::chrono::milliseconds>(stop_w0 - start_w0);
        xadd_times.push_back(std::to_string(dur_w0.count()));
        //     time XADD end ---- 

        //---- time XADD read start
        std::chrono::time_point<std::chrono::high_resolution_clock> start_r0 = std::chrono::high_resolution_clock::now();    
        boost::system::error_code xaddr_err;
        auto result_markers = bredis_con.read(rx_buff, xaddr_err);
        if(xaddr_err){
            std::cout<<"ERROR: " <<xaddr_err.message()<<std::endl;        
        }
        
        std::chrono::time_point<std::chrono::high_resolution_clock> stop_r0 = std::chrono::high_resolution_clock::now();
        auto dur_r0 = std::chrono::duration_cast<std::chrono::milliseconds>(stop_r0 - start_r0);
        xadd_read_times.push_back(std::to_string(dur_r0.count()));
        //     time XADD read end ---- 

        //---- time XADD extract start
        error_extractor<Iterator> err_extract;
        std::chrono::time_point<std::chrono::high_resolution_clock> start_e0 = std::chrono::high_resolution_clock::now();   
        auto err = boost::apply_visitor(err_extract, result_markers.result);
        if(!err.empty()){
            std::cout<<"REDIS XADD ERROR @ iter:" << i << ": "<< err<< std::endl;
        }
        std::chrono::time_point<std::chrono::high_resolution_clock> stop_e0 = std::chrono::high_resolution_clock::now();
        auto dur_e0 = std::chrono::duration_cast<std::chrono::milliseconds>(stop_e0 - start_e0);
        xadd_extract_times.push_back(std::to_string(dur_e0.count()));
        //     time XADD extract end ---- 

        // consume the buffers, after finishing work with the markers
        rx_buff.consume(result_markers.consumed);
        

    }

    //end write timer
    std::chrono::time_point<std::chrono::high_resolution_clock> stop_w = std::chrono::high_resolution_clock::now();
    auto dur_w = std::chrono::duration_cast<std::chrono::milliseconds>(stop_w - start_w);


    //start read timer
    std::chrono::time_point<std::chrono::high_resolution_clock> start_r = std::chrono::high_resolution_clock::now();
    
    for(int i = 0; i < iters; i++){
        //---- time XRANGE start
        std::chrono::time_point<std::chrono::high_resolution_clock> start_w0 = std::chrono::high_resolution_clock::now();
        
        boost::system::error_code xrange_err;        
        bredis_con.write(bredis::single_command_t{ "XRANGE" , "bredis",  "-", "+", "COUNT", "10"}, xrange_err);
        if(xrange_err){
            std::cout<<"ERROR: " <<xrange_err.message()<<std::endl;        
        }

        std::chrono::time_point<std::chrono::high_resolution_clock> stop_w0 = std::chrono::high_resolution_clock::now();
        auto dur_w0 = std::chrono::duration_cast<std::chrono::milliseconds>(stop_w0 - start_w0);
        xrange_times.push_back(std::to_string(dur_w0.count()));
        //     time XRANGE end ---- 

        //---- time XRANGE read start
        std::chrono::time_point<std::chrono::high_resolution_clock> start_r0 = std::chrono::high_resolution_clock::now();
        
        boost::system::error_code xranger_err;        
        auto result_markers = bredis_con.read(tx_buff, xranger_err);
        if(xranger_err){
            std::cout<<"ERROR: " <<xranger_err.message()<<std::endl;        
        }

        std::chrono::time_point<std::chrono::high_resolution_clock> stop_r0 = std::chrono::high_resolution_clock::now();
        auto dur_r0 = std::chrono::duration_cast<std::chrono::milliseconds>(stop_r0 - start_r0);
        xrange_read_times.push_back(std::to_string(dur_r0.count()));
        //     time XRANGE read end ---- 

        //---- time XRANGE extract start
        std::chrono::time_point<std::chrono::high_resolution_clock> start_e0 = std::chrono::high_resolution_clock::now();

//        auto extract3 = boost::apply_visitor(bredis::extractor<Iterator>(), result_markers.result);

        error_extractor<Iterator> err_extract;
        auto err = boost::apply_visitor(err_extract, result_markers.result);
        if(!err.empty()){
            std::cout<<"REDIS XRANGE ERROR @ iter:" << i << ": "<< err<< std::endl;
        }

        std::chrono::time_point<std::chrono::high_resolution_clock> stop_e0 = std::chrono::high_resolution_clock::now();
        auto dur_e0 = std::chrono::duration_cast<std::chrono::milliseconds>(stop_e0 - start_e0);
        xrange_extract_times.push_back(std::to_string(dur_e0.count()));
        //    time XRANGE extract end ---- 


        //---- time XRANGE custom  extract start
        std::chrono::time_point<std::chrono::high_resolution_clock> start_e1 = std::chrono::high_resolution_clock::now();

        auto extract_ = boost::apply_visitor(bredis::extractor<Iterator>(), result_markers.result);

        error_extractor<Iterator> err_extract_;
        auto err_ = boost::apply_visitor(err_extract_, result_markers.result);
        if(!err.empty()){
            std::cout<<"REDIS XRANGE1 ERROR @ iter:" << i << ": "<< err_<< std::endl;
        }

        std::chrono::time_point<std::chrono::high_resolution_clock> stop_e1 = std::chrono::high_resolution_clock::now();
        auto dur_e1 = std::chrono::duration_cast<std::chrono::milliseconds>(stop_e1 - start_e1);
        xrange_extract_times1.push_back(std::to_string(dur_e1.count()));
        //    time XRANGE custom extract end ---- 


        tx_buff.consume(result_markers.consumed);

    }

    //end read timer
    std::chrono::time_point<std::chrono::high_resolution_clock> stop_r = std::chrono::high_resolution_clock::now();
    auto dur_r = std::chrono::duration_cast<std::chrono::milliseconds>(stop_r - start_r);

    
    //Printout the xadd stats...
    std::cout<<"\n----For Writing----"<<std::endl;
    std::cout<<"Total Elapsed Time for bredis client (" << iters<< "x): "<< dur_w.count()
          << " ms.\n"<< "Average Time for bredis client msg write (XADD): "<< (dur_w/(float)iters).count()
          << " ms"<<std::endl;

    //Printout the xrange stats...
    std::cout<<"----For Reading----"<<std::endl;
    std::cout<<"Total Elapsed Time for bredis client (" << iters<< "x): "<< dur_r.count()
          << " ms.\n"<< "Average Time for bredis client msg read (XRANGE): "<< (dur_r/(float)iters).count()
          << " ms"<<std::endl;


    //Store the timing in the logfile
    for(int i = 0; i < xrange_times.size(); i++){
        bredis_logfile << xadd_times[i] + ", " + xadd_read_times[i] + ", " +  xadd_extract_times[i] + ", "  
                        + xrange_times[i] + ", " + xrange_read_times[i] +  ", " + xrange_extract_times[i] + ", " + xrange_extract_times1[i] + "\n";
    }

    bredis_logfile.close(); 

    ioserv.run();

}