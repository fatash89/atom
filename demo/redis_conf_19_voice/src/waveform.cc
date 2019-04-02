#include <iostream>
#include <atomcpp/element.h>
#include <assert.h>
#include <unistd.h>
#include <thread>
#include <math.h>

// How frequently to publish the waveform data, in Hz
double wavefrom_update_hz = 1000.0;

// Period of the waveform, in seconds
double waveform_period = 1.0;

// Element itself. Shared between a few threads. Elements are multi-thread
//  safe.
atom::Element *element = NULL;

// Command to change the period of the waveform
class ChangePeriodCommand: public atom::CommandMsgpack<double,std::nullptr_t> {
public:

    // Use the base class constructor
    using atom::CommandMsgpack<double,std::nullptr_t>::CommandMsgpack;

    // Validate the request. Make sure it's a valid waveform type
    virtual bool validate() {

        if ((*req_data >= -.1) && (*req_data <= 10.0)) {
            return true;
        } else {
            return false;
        }
    }

    // Change the waveform type
    virtual bool run() {

        waveform_period = *req_data;
        return true;
    }
};

// Command to change the frequency at which points are published
class ChangePublishRateCommand: public atom::CommandMsgpack<double,std::nullptr_t> {
public:

    // Use the base class constructor
    using atom::CommandMsgpack<double,std::nullptr_t>::CommandMsgpack;

    // Validate the request. Make sure it's a valid waveform type
    virtual bool validate() {

        if ((*req_data >= 1.0) && (*req_data <= 10000.0)) {
            return true;
        } else {
            return false;
        }
    }

    // Change the waveform type
    virtual bool run() {

        wavefrom_update_hz = *req_data;
        return true;
    }
};

// Simple data + len callback for the "hello" command.
bool hello_world_callback(
    const uint8_t* data,
    size_t data_len,
    atom::ElementResponse *resp,
    void *user_data)
{
    resp->setData("hello, " + std::string((const char *)data, data_len));
    return true;
}

// Command handling thread
void accept_commands()
{
    // Add a basic command handler
    element->addCommand(
        "hello",
        "responds with \"hello, world\" plus whatever data you sent",
        hello_world_callback,
        NULL,
        1000);

    // Add in the waveform switching command handler
    element->addCommand(
        new ChangePeriodCommand(
            "period",
            "changes the period of the waveform to the passed value, in seconds",
            1000));

    // Add in the waveform switching command handler
    element->addCommand(
        new ChangePublishRateCommand(
            "rate",
            "changes the publishing rate of the waveform",
            1000));

    element->commandLoop();
}

int main(int argc, char **argv) {

    // Make the waveform element
    element = new atom::Element("waveform");
    assert(element != NULL);

    // Make the thread for the waveform command handler
    std::thread command_thread(accept_commands);

    // Loop forever, publishing data
    while (true) {

        // Assume it takes 0s to publish for now, which is not really
        //  true. Can improve this later
        usleep(1000000.0 / wavefrom_update_hz);

        // Publish data based on the current time
        struct timespec now;
        clock_gettime(CLOCK_MONOTONIC, &now);

        // Figure out how many nanoseconds we've been up for
        double seconds = (double)now.tv_sec + ((double)now.tv_nsec / 1000000000.0);

        // Based on the current waveform type, figure out which
        //  type of waveform to publish
        double t_val = ((seconds * 2 * M_PI) / waveform_period);

        double sin_val = sin(t_val);
        double cos_val = cos(t_val);
        double tan_val = tan(t_val);

        // Want to msgpack the data so it's compressed/easier to interpret
        //  on the wire
        std::stringstream sin_buffer, cos_buffer, tan_buffer;
        msgpack::pack(sin_buffer, sin_val);
        msgpack::pack(cos_buffer, cos_val);
        msgpack::pack(tan_buffer, tan_val);

        // Dictionary of k:v pairs we'll publish
        atom::entry_data_t data;
        data["sin"] = sin_buffer.str();
        data["cos"] = cos_buffer.str();
        data["tan"] = tan_buffer.str();

        // And perform the publish
        enum atom_error_t err = element->entryWrite(
            "serialized",
            data);
        assert (err == ATOM_NO_ERROR);

        // We can also publish an unserialized version
        atom::entry_data_t unserialized_data;
        unserialized_data["sin"] = std::string(
            (char*)&sin_val, sizeof(sin_val));
        unserialized_data["cos"] = std::string(
            (char*)&cos_val, sizeof(cos_val));
        unserialized_data["tan"] = std::string(
            (char*)&tan_val, sizeof(tan_val));

         err = element->entryWrite(
            "unserialized",
            unserialized_data);
        assert (err == ATOM_NO_ERROR);
    }


    return 0;
}
